"""
Compliance-Diff Agent -- legal judgment only, not clause matching.

This agent answers a different question from agents/lease_parser.py: given
that a lease clause was found that addresses a legal requirement, does the
clause actually satisfy what the law requires? It reads from lease_clauses
(populated by the parser) and legal_sources and writes its verdicts to
compliance_findings.

Why this is a separate agent from lease_parser.py
--------------------------------------------------
Clause matching and compliance judgment are different reasoning tasks:

  - Matching asks: "Is there any text in this lease that talks about this
    topic?" It can tolerate ambiguity and runs cheaply as a retrieval
    problem. The parser answers this.
  - Judgment asks: "Does what the lease says actually satisfy the precise
    requirements of the statute?" It requires the full statutory text, careful
    legal reasoning, and a conservative bias toward flagging uncertainty. That
    is what this agent does.

Conflating the two into one prompt degrades both. Keeping them separate means
each can be improved, swapped, or retried independently.

Why awareness-tier items are excluded
--------------------------------------
legal_sources.check_tier distinguishes two kinds of requirements:

  - 'requirement': a specific obligation that should appear as a clause in the
    lease. This agent can render a compliance verdict because there is a
    specific lease clause to compare against the statutory text.
  - 'awareness': background legal context that a landlord should know but that
    does not map to a specific checkable lease clause (e.g. "Fair Housing Act
    applies to residential rentals"). There is no lease clause to judge against,
    so there is no verdict for this agent to make. Awareness items are surfaced
    at report-generation time in a later phase.

confidence = -1.0 sentinel
---------------------------
Any row in lease_clauses with confidence = -1.0 was never actually judged by
the parser -- it received a placeholder because the API call failed during
Phase 3. This agent treats those rows as 'needs_reparse' and does not attempt
to render a compliance verdict on them, since the underlying clause match is
unknown. They are listed by name in the summary so they are visible and
actionable.

Tool use is forced (tool_choice="tool") so responses are always structured JSON.

Related-provision context (eval-driven fix)
--------------------------------------------
An eval suite finding revealed that judging each requirement in isolation
is insufficient: legal_sources contains subsections that explicitly modify
each other, and the judgment prompt had no way to know about them. A real
example: 68 P.S. § 250.501(e) explicitly permits a landlord and tenant to
agree in writing to a shorter notice period than the default in § 501(a)-(b).
When the compliance-diff agent evaluated a lease's notice-waiver clause
against § 501(a)-(b) alone, it had no visibility into § 501(e) and
incorrectly returned 'contradicts' on what was actually a compliant exercise
of the permitted exception.

The fix: classify_compliance now calls get_related_context() per row before
building each requirement's prompt section. This pulls two kinds of related
statutory text from the database:

  1. Other rows that share the same family_key (subsections of the same
     statutory section, e.g. all clauses of § 511.1).
  2. Rows whose family_key appears in family_cross_references as connected
     to this row's family_key within the same jurisdiction (cross-section
     references detected automatically during ingestion).

Both are shown under a clear heading in the prompt so the model can take
modifying provisions into account before concluding that a lease clause
contradicts a base rule.
"""

import sys
from typing import Any

import anthropic

from api.config import settings
from api.db import get_connection

# Maximum requirements per Claude call. Matches lease_parser.py's _BATCH_SIZE
# convention: keeping batches at ~25 prevents the model from losing track of
# individual keys in a long list and keeps max_tokens headroom comfortable.
_BATCH_SIZE = 25

# confidence sentinel value from lease_parser.py: a row with this value was
# never actually judged -- the Phase 3 API call failed. It cannot appear as
# real LLM output because _validate_classification in lease_parser.py clamps
# all real confidence values to [0, 1].
_FAILED_CONFIDENCE_SENTINEL = -1.0

# Status values allowed by the compliance_findings CHECK constraint.
_ALLOWED_STATUSES = {"compliant", "contradicts", "needs_review"}


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

RequirementRow = dict[str, Any]   # one row joining legal_sources + lease_clauses
Finding = dict[str, Any]          # one validated entry; may include
                                  # "processing_error": True for API failures


# ---------------------------------------------------------------------------
# Anthropic tool definition
# ---------------------------------------------------------------------------

_RECORD_COMPLIANCE_FINDINGS_TOOL: dict[str, Any] = {
    "name": "record_compliance_findings",
    "description": (
        "Record a compliance verdict for each lease clause compared against its "
        "legal requirement. For each item, decide whether the lease clause clearly "
        "and fully satisfies what the law requires, contradicts it, or needs human "
        "review. Write plain-language explanations a landlord can understand."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "description": "One entry per requirement_key supplied in the prompt.",
                "items": {
                    "type": "object",
                    "properties": {
                        "requirement_key": {
                            "type": "string",
                            "description": "Exactly as supplied in the prompt.",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["compliant", "contradicts", "needs_review"],
                            "description": (
                                "compliant: the lease clause clearly and fully satisfies "
                                "the legal requirement. contradicts: the lease clause "
                                "actively conflicts with the requirement. needs_review: "
                                "the match is weak, partial, or ambiguous -- err toward "
                                "this when uncertain."
                            ),
                        },
                        "explanation": {
                            "type": "string",
                            "description": (
                                "Plain-language reasoning referencing what the lease says "
                                "vs what the law requires, written for a landlord to "
                                "understand. Must not be empty."
                            ),
                        },
                    },
                    "required": ["requirement_key", "status", "explanation"],
                },
            }
        },
        "required": ["findings"],
    },
}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_requirement_tier_rows(conn, lease_id: str) -> dict[str, list]:
    """Query all active requirement-tier rows and split them into four groups.

    Queries legal_sources for all active check_tier='requirement' rows, then
    left-joins to lease_clauses for this lease_id. Every requirement_key lands
    in exactly one of four output groups:

    - ``missing``: not present in lease_clauses at all for this lease_id.
      Distinct from "confirmed absent" -- this requirement was never parsed.
    - ``needs_reparse``: present with confidence = -1.0 (Phase 3 API failure
      sentinel; the clause match was never actually judged).
    - ``absent``: present with confidence != -1.0 and clause_text IS NULL
      (the parser confirmed no matching clause was found).
    - ``needs_judgment``: present with confidence != -1.0 and clause_text IS
      NOT NULL (a matching clause was found; this agent renders a verdict).

    Parameters
    ----------
    conn:
        An open psycopg connection obtained via ``get_connection()``.
    lease_id:
        UUID string of the lease to check.

    Returns
    -------
    dict with keys ``"missing"``, ``"needs_reparse"``, ``"absent"``,
    ``"needs_judgment"``. Each value is a list of row dicts. ``needs_judgment``
    rows include ``requirement_key``, ``citation``, ``full_text``,
    ``clause_text``, ``family_key``, and ``jurisdiction`` for use in the
    compliance prompt and related-context lookup.

    Raises
    ------
    ValueError
        If lease_id has zero rows in lease_clauses at all, indicating
        agents.lease_parser has not been run for this lease.
    """
    # Check whether this lease_id has been parsed at all.
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM lease_clauses WHERE lease_id = %s",
            (lease_id,),
        )
        count = cur.fetchone()[0]

    if count == 0:
        raise ValueError(
            f"lease_id '{lease_id}' has no rows in lease_clauses. "
            "Run agents.lease_parser on this lease before running compliance_diff."
        )

    # Left-join legal_sources (requirement-tier only) to lease_clauses.
    # family_key and jurisdiction are included so classify_compliance can call
    # get_related_context() per row when building the judgment prompt.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                ls.requirement_key,
                ls.citation,
                ls.full_text,
                ls.summary,
                ls.family_key,
                ls.jurisdiction,
                lc.clause_text,
                lc.confidence
            FROM legal_sources ls
            LEFT JOIN lease_clauses lc
                ON lc.requirement_key = ls.requirement_key
                AND lc.lease_id = %(lease_id)s
            WHERE ls.status = 'active'
              AND ls.check_tier = 'requirement'
            ORDER BY ls.jurisdiction, ls.requirement_key
            """,
            {"lease_id": lease_id},
        )
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]

    missing: list[RequirementRow] = []
    needs_reparse: list[RequirementRow] = []
    absent: list[RequirementRow] = []
    needs_judgment: list[RequirementRow] = []

    for row in rows:
        record = dict(zip(columns, row))
        confidence = record["confidence"]
        clause_text = record["clause_text"]

        if confidence is None:
            # Left join produced no matching lease_clauses row.
            missing.append(record)
        elif float(confidence) == _FAILED_CONFIDENCE_SENTINEL:
            needs_reparse.append(record)
        elif clause_text is None:
            absent.append(record)
        else:
            needs_judgment.append(record)

    return {
        "missing": missing,
        "needs_reparse": needs_reparse,
        "absent": absent,
        "needs_judgment": needs_judgment,
    }


def _delete_existing_findings(conn, lease_id: str) -> None:
    """Delete any previously stored compliance findings for this lease_id.

    Called before inserting new results so that rerunning compliance_diff for
    the same lease_id replaces prior results rather than accumulating
    duplicates.

    Parameters
    ----------
    conn:
        An open psycopg connection with ``autocommit=True``.
    lease_id:
        UUID string identifying the lease being reprocessed.
    """
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM compliance_findings WHERE lease_id = %s", (lease_id,)
        )


def _insert_findings(conn, lease_id: str, findings: list[Finding]) -> None:
    """Bulk-insert validated compliance findings into compliance_findings.

    The internal ``processing_error`` field is not written to the database --
    only the four schema columns are inserted. verifier_confirmed is left at
    its column default; setting it is the verifier agent's job in a later phase.

    Parameters
    ----------
    conn:
        An open psycopg connection with ``autocommit=True``.
    lease_id:
        UUID string identifying the lease these findings belong to.
    findings:
        Validated entries, each containing ``requirement_key``, ``status``,
        and ``explanation``.
    """
    if not findings:
        return

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO compliance_findings
                (lease_id, requirement_key, status, explanation)
            VALUES (%s, %s, %s, %s)
            """,
            [
                (
                    lease_id,
                    f["requirement_key"],
                    f["status"],
                    f["explanation"],
                )
                for f in findings
            ],
        )


def _insert_absent_findings(
    conn, lease_id: str, absent_rows: list[RequirementRow]
) -> None:
    """Insert status='absent' findings for requirements with no matching clause.

    No LLM call is needed: the parser already confirmed no clause was found.
    The explanation references the citation so the finding is self-contained
    when read from compliance_findings without joining back to legal_sources.

    Parameters
    ----------
    conn:
        An open psycopg connection with ``autocommit=True``.
    lease_id:
        UUID string identifying the lease.
    absent_rows:
        Rows from the 'absent' group returned by ``get_requirement_tier_rows``.
    """
    if not absent_rows:
        return

    findings: list[Finding] = [
        {
            "requirement_key": row["requirement_key"],
            "status": "absent",
            "explanation": (
                f"This lease does not appear to address this requirement "
                f"({row['citation']})."
            ),
        }
        for row in absent_rows
    ]
    _insert_findings(conn, lease_id, findings)


# ---------------------------------------------------------------------------
# Related-provision context
# ---------------------------------------------------------------------------

def get_related_context(
    conn,
    requirement_key: str,
    family_key: str | None,
    jurisdiction: str,
) -> str:
    """Build a context string containing related and cross-referenced provisions.

    Called per-row in classify_compliance's prompt-building loop so the
    judgment model can see statutory provisions that may modify or qualify the
    base requirement being judged. This prevents false 'contradicts' verdicts
    when a lease clause relies on a permitted exception in a sibling subsection.

    Two sources of related content are fetched:

    1. **Same-family members**: all other active rows in legal_sources that
       share this row's ``family_key`` (e.g. all subsections of § 511.1).
       Not filtered by check_tier -- awareness-tier siblings are still valid
       context for understanding how the requirement applies.

    2. **Cross-referenced families**: rows whose family_key appears on either
       side of a family_cross_references relationship connected to this row's
       family_key within the same jurisdiction. The relationship is treated as
       bidirectional regardless of which direction it was detected in source
       text. Not filtered by check_tier for the same reason as above.

    Deduplication: a requirement_key that qualifies for both sections is only
    included once (in the same-family section). The current data model makes
    this unlikely, but the guard is cheap and correct.

    At the current corpus size (largest family has 8 members), this adds a
    modest, acceptable amount of extra context per row. If the corpus grows
    substantially later, revisit whether a cap on the number of related items
    shown per row is needed to control prompt size -- not needed now.

    Parameters
    ----------
    conn:
        An open psycopg connection.
    requirement_key:
        The key being judged -- excluded from the same-family results so a row
        does not show its own text as related context.
    family_key:
        The family_key of the row being judged. If None, returns ``""``
        immediately since no family grouping is possible.
    jurisdiction:
        Used to scope the family_cross_references lookup so cross-references
        from a different jurisdiction are not shown.

    Returns
    -------
    str
        A formatted multi-section string, or ``""`` if no related content
        exists. The caller can test truthiness to decide whether to include
        the context block in the prompt.
    """
    if family_key is None:
        return ""

    # 1. Same-family members (other subsections of the same statutory section).
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT requirement_key, citation, full_text
            FROM legal_sources
            WHERE status = 'active'
              AND family_key = %(family_key)s
              AND requirement_key != %(requirement_key)s
            ORDER BY requirement_key
            """,
            {"family_key": family_key, "requirement_key": requirement_key},
        )
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
    same_family_rows = [dict(zip(columns, row)) for row in rows]

    # 2. Resolve cross-referenced family keys (bidirectional lookup).
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT
                CASE WHEN source_family_key = %(family_key)s
                     THEN target_family_key
                     ELSE source_family_key
                END AS related_family_key
            FROM family_cross_references
            WHERE (source_family_key = %(family_key)s
                   OR target_family_key = %(family_key)s)
              AND jurisdiction = %(jurisdiction)s
            """,
            {"family_key": family_key, "jurisdiction": jurisdiction},
        )
        related_family_keys = [row[0] for row in cur.fetchall()]

    # Fetch rows for each cross-referenced family.
    cross_ref_rows: list[dict] = []
    for rfk in related_family_keys:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT requirement_key, citation, full_text
                FROM legal_sources
                WHERE status = 'active'
                  AND family_key = %(rfk)s
                ORDER BY requirement_key
                """,
                {"rfk": rfk},
            )
            sub_rows = cur.fetchall()
            sub_cols = [desc[0] for desc in cur.description]
        cross_ref_rows.extend([dict(zip(sub_cols, row)) for row in sub_rows])

    # Deduplicate cross-ref rows against same-family rows (and self).
    seen_keys: set[str] = {requirement_key} | {r["requirement_key"] for r in same_family_rows}
    deduped_cross_ref: list[dict] = []
    for row in cross_ref_rows:
        if row["requirement_key"] not in seen_keys:
            seen_keys.add(row["requirement_key"])
            deduped_cross_ref.append(row)

    if not same_family_rows and not deduped_cross_ref:
        return ""

    parts: list[str] = []
    for row in same_family_rows:
        parts.append(
            f"Related provision in the same section ({row['citation']}):\n"
            f"{row['full_text']}"
        )
    for row in deduped_cross_ref:
        parts.append(
            f"Cross-referenced provision ({row['citation']}):\n"
            f"{row['full_text']}"
        )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_finding(
    entry: Any,
    expected_keys: set[str],
    batch_label: str,
) -> Finding | None:
    """Validate one compliance finding entry returned by Claude.

    Checks in order:
      1. Must be a dict.
      2. ``requirement_key`` must be a non-empty string.
      3. ``requirement_key`` must be in ``expected_keys`` (hallucination guard).
      4. ``status`` must be one of the three allowed values.
      5. ``explanation`` must be a non-empty, non-whitespace-only string. The
         database column is NOT NULL; a silent empty value would be an invisible
         data-quality problem.

    Parameters
    ----------
    entry:
        Raw object from the tool_use ``findings`` array.
    expected_keys:
        Requirement keys sent to this specific batch. Any key not in this set
        is rejected to prevent hallucinated or mistyped keys creating orphaned
        rows in compliance_findings.
    batch_label:
        Short string like ``"batch 2/4"`` used in warning messages.

    Returns
    -------
    Finding or None
        The validated entry, or None if it must be skipped.
    """
    if not isinstance(entry, dict):
        print(f"  [WARN] {batch_label}: skipping non-dict finding entry: {entry!r}")
        return None

    key = entry.get("requirement_key")
    status = entry.get("status")
    explanation = entry.get("explanation")

    if not isinstance(key, str) or not key:
        print(
            f"  [WARN] {batch_label}: skipping entry with missing/invalid "
            f"requirement_key: {entry!r}"
        )
        return None

    if key not in expected_keys:
        print(
            f"  [WARN] {batch_label}: skipping '{key}' -- not in the set of "
            "requirement_keys sent to Claude for this batch "
            "(hallucinated or mistyped key)."
        )
        return None

    if status not in _ALLOWED_STATUSES:
        print(
            f"  [WARN] {batch_label}: skipping '{key}' -- status {status!r} is not "
            f"one of {sorted(_ALLOWED_STATUSES)}."
        )
        return None

    if not isinstance(explanation, str) or not explanation.strip():
        print(
            f"  [WARN] {batch_label}: skipping '{key}' -- explanation is missing, "
            "non-string, or whitespace-only (compliance_findings.explanation is NOT NULL)."
        )
        return None

    return {
        "requirement_key": key,
        "status": status,
        "explanation": explanation,
    }


# ---------------------------------------------------------------------------
# LLM compliance judgment
# ---------------------------------------------------------------------------

def classify_compliance(
    conn,
    rows_needing_judgment: list[RequirementRow],
) -> list[Finding]:
    """Run Claude compliance judgment on requirements with matched lease clauses.

    Each batch shows both the full statutory text and the matched lease clause
    side by side. For each requirement, get_related_context() is called to
    fetch sibling subsections (same family_key) and cross-referenced provisions
    (family_cross_references) that may modify how the base rule applies. When
    present, these are shown under a dedicated heading so the model can take
    permitted exceptions into account before concluding a lease clause
    contradicts the law.

    The prompt explicitly instructs Claude to use 'needs_review' when uncertain
    rather than forcing 'compliant', because a missed real compliance issue is
    worse than an unnecessary review flag.

    On API failure or a missing tool_use block, returns placeholder findings
    (status='needs_review', processing_error=True) for every affected
    requirement_key, with an explanation prefixed "[AUTOMATED CHECK FAILED]"
    so they are visibly distinguishable from genuinely-judged needs_review
    findings in the explanation text itself (compliance_findings has no
    separate column for this flag). The affected keys are logged by name.

    Parameters
    ----------
    conn:
        An open psycopg connection used to fetch related context per row via
        ``get_related_context``. Must remain open for the duration of this call.
    rows_needing_judgment:
        Rows from the 'needs_judgment' group returned by
        ``get_requirement_tier_rows``. Each row must contain
        ``requirement_key``, ``citation``, ``full_text``, ``clause_text``,
        ``family_key``, and ``jurisdiction``.

    Returns
    -------
    list[Finding]
        One entry per input row, including processing-error placeholders for
        any batch that failed. Entries may carry a ``"processing_error": True``
        field (not written to the database) used by ``run_compliance_diff``
        to distinguish API failures from genuine needs_review judgments in the
        printed summary.
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    all_keys = [row["requirement_key"] for row in rows_needing_judgment]
    rows_by_key = {row["requirement_key"]: row for row in rows_needing_judgment}

    batches = [
        all_keys[i : i + _BATCH_SIZE] for i in range(0, len(all_keys), _BATCH_SIZE)
    ]
    total_batches = len(batches)
    all_results: list[Finding] = []

    for batch_idx, batch_keys in enumerate(batches, start=1):
        batch_label = f"batch {batch_idx}/{total_batches}"
        expected_keys = set(batch_keys)

        sections: list[str] = []
        for key in batch_keys:
            row = rows_by_key[key]
            section = (
                f"REQUIREMENT: {key}\n"
                f"Citation: {row['citation']}\n"
                f"What the law requires:\n{row['full_text']}\n\n"
                f"What the lease says:\n{row['clause_text']}"
            )
            related = get_related_context(
                conn,
                requirement_key=key,
                family_key=row.get("family_key"),
                jurisdiction=row["jurisdiction"],
            )
            if related:
                section += (
                    "\n\nAdditional context -- related and cross-referenced "
                    "provisions that may modify how this requirement applies:\n"
                    + related
                )
            sections.append(section)

        prompt = (
            "You are a legal compliance reviewer helping a Pittsburgh-area landlord "
            "understand whether their lease satisfies specific legal requirements.\n\n"
            "For each REQUIREMENT below, you are given the full statutory text and "
            "the matching clause from the lease. Decide whether the lease clause:\n"
            "  - 'compliant': clearly and fully satisfies what the law requires\n"
            "  - 'contradicts': actively conflicts with or violates the requirement\n"
            "  - 'needs_review': the match is weak, partial, tangential, or ambiguous\n\n"
            "Some legal provisions are modified or qualified by related provisions "
            "shown above -- for example, a default rule may be explicitly overridable "
            "if the lease says so. Take this related context into account before "
            "concluding a lease clause contradicts the law; a clause that diverges "
            "from a base rule may still be compliant if a related provision explicitly "
            "permits it.\n\n"
            "IMPORTANT: if the lease clause doesn't clearly and fully address what "
            "the law requires, or the match feels weak or tangential, use "
            "'needs_review' rather than forcing 'compliant'. Err toward flagging "
            "when uncertain -- a missed real compliance issue is worse than an "
            "unnecessary review flag.\n\n"
            "Write explanations in plain language a landlord can understand, "
            "referencing specifically what the lease says vs what the law requires. "
            "Do not use legal jargon.\n\n"
            + "\n\n---\n\n".join(sections)
            + "\n\nCall record_compliance_findings with one entry per REQUIREMENT listed above."
        )

        print(f"  [{batch_label}] Judging {len(batch_keys)} requirements ...")

        try:
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=4096,
                tools=[_RECORD_COMPLIANCE_FINDINGS_TOOL],
                tool_choice={
                    "type": "tool",
                    "name": "record_compliance_findings",
                },
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            failed_keys_str = ", ".join(sorted(batch_keys))
            print(
                f"  [ERROR] {batch_label}: Anthropic API call failed -- {exc}\n"
                f"  Failed requirement_keys: {failed_keys_str}"
            )
            for key in batch_keys:
                all_results.append({
                    "requirement_key": key,
                    "status": "needs_review",
                    "explanation": (
                        "[AUTOMATED CHECK FAILED] The compliance judgment API call "
                        f"failed for this requirement. Manual review required. Error: {exc}"
                    ),
                    "processing_error": True,
                })
            continue

        tool_block = next(
            (block for block in response.content if block.type == "tool_use"),
            None,
        )
        if tool_block is None:
            failed_keys_str = ", ".join(sorted(batch_keys))
            print(
                f"  [ERROR] {batch_label}: no tool_use block in response.\n"
                f"  Failed requirement_keys: {failed_keys_str}"
            )
            for key in batch_keys:
                all_results.append({
                    "requirement_key": key,
                    "status": "needs_review",
                    "explanation": (
                        "[AUTOMATED CHECK FAILED] The compliance judgment API call "
                        "returned no structured output for this requirement. "
                        "Manual review required."
                    ),
                    "processing_error": True,
                })
            continue

        raw_entries: list[Any] = tool_block.input.get("findings", [])

        validated: list[Finding] = []
        for entry in raw_entries:
            result = _validate_finding(entry, expected_keys, batch_label)
            if result is not None:
                validated.append(result)

        # Warn about keys Claude omitted entirely.
        returned_keys = {f["requirement_key"] for f in validated}
        missing_keys = expected_keys - returned_keys
        if missing_keys:
            print(
                f"  [WARN] {batch_label}: Claude did not return findings for: "
                + ", ".join(sorted(missing_keys))
            )

        all_results.extend(validated)

    return all_results


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_compliance_diff(lease_id: str) -> None:
    """Run full compliance judgment for all requirement-tier items in a lease.

    Reads from lease_clauses (populated by agents/lease_parser.py) and
    legal_sources, writes verdicts to compliance_findings. Idempotent: any
    existing compliance_findings rows for this lease_id are deleted before
    writing new results.

    Four-way split on input:
      - missing: requirement_keys never parsed for this lease -- listed by name
        in the summary, the most actionable category.
      - needs_reparse: Phase 3 classified these with confidence=-1.0 (API
        failure sentinel); a compliance verdict cannot be rendered without a
        confirmed clause match.
      - absent: no matching lease clause found (confidence != -1.0, clause_text
        IS NULL); inserted directly as status='absent', no LLM call.
      - needs_judgment: a matching clause was found; sent to Claude for verdict.

    Parameters
    ----------
    lease_id:
        UUID string of a lease that has already been processed by
        agents/lease_parser.py. If the lease has no rows in lease_clauses at
        all, a ValueError is raised naming the lease_id and stating that
        agents.lease_parser must be run first.
    """
    print(f"Running compliance diff for lease {lease_id} ...")

    conn = get_connection()

    try:
        groups = get_requirement_tier_rows(conn, lease_id)

        missing = groups["missing"]
        needs_reparse = groups["needs_reparse"]
        absent = groups["absent"]
        needs_judgment = groups["needs_judgment"]

        total = len(missing) + len(needs_reparse) + len(absent) + len(needs_judgment)
        print(f"Found {total} active requirement-tier items.")
        print(f"  {len(needs_judgment)} have matched clauses (will be judged by LLM).")
        print(f"  {len(absent)} confirmed absent (no LLM call needed).")
        print(f"  {len(needs_reparse)} need reparse (Phase 3 API failure).")
        print(f"  {len(missing)} were never parsed for this lease.")

        # Idempotency: delete any prior findings before writing.
        _delete_existing_findings(conn, lease_id)

        # Insert absent findings directly -- no LLM call needed.
        _insert_absent_findings(conn, lease_id, absent)

        # Run LLM judgment on requirements with matched clauses.
        llm_findings: list[Finding] = []
        if needs_judgment:
            print(f"\nSending {len(needs_judgment)} requirements for compliance judgment ...")
            llm_findings = classify_compliance(conn, needs_judgment)
            _insert_findings(conn, lease_id, llm_findings)

        # Build summary stats, splitting needs_review into judged vs error.
        status_counts: dict[str, int] = {"compliant": 0, "contradicts": 0}
        judged_needs_review = 0
        error_needs_review = 0
        error_keys: list[str] = []

        for f in llm_findings:
            if f.get("processing_error"):
                error_needs_review += 1
                error_keys.append(f["requirement_key"])
            elif f["status"] == "needs_review":
                judged_needs_review += 1
            else:
                status_counts[f["status"]] = status_counts.get(f["status"], 0) + 1

        print(f"\n{'=' * 60}")
        print(f"Compliance diff summary for lease {lease_id}:")
        print(f"  Total requirement-tier items:  {total}")
        print(f"  Absent (no clause found):      {len(absent)}")
        print(f"  Compliant:                     {status_counts.get('compliant', 0)}")
        print(f"  Contradicts:                   {status_counts.get('contradicts', 0)}")
        print(f"  Needs review (judged):         {judged_needs_review}")
        print(f"  Needs review (API error):      {error_needs_review}")
        if error_keys:
            print(f"    Error keys: {', '.join(sorted(error_keys))}")
        if needs_reparse:
            reparse_keys = ", ".join(
                sorted(r["requirement_key"] for r in needs_reparse)
            )
            print(f"  Needs reparse ({len(needs_reparse)}):            {reparse_keys}")
        if missing:
            missing_keys = ", ".join(
                sorted(r["requirement_key"] for r in missing)
            )
            print(
                f"  Never parsed ({len(missing)}) -- run lease_parser first:\n"
                f"    {missing_keys}"
            )
        print(f"{'=' * 60}")

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python agents/compliance_diff.py <lease_id>")
        sys.exit(1)

    run_compliance_diff(sys.argv[1])
