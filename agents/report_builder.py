"""
Report Builder -- pure data assembly from already-computed pipeline results.

This module is the final phase of the Pitt-Lords compliance pipeline. It
reads from compliance_findings (written by agents/compliance_diff.py and
updated by agents/verifier.py) and lease_clauses (written by
agents/lease_parser.py) and assembles a structured JSON report. It makes
NO LLM calls -- every judgment in the output was made by an earlier phase.

Three "unknown state vs confirmed finding" traps this module explicitly guards
against
-----------------------------------------------------------------------

Trap 1: never_parsed vs confirmed-absent (awareness items)
  A LEFT JOIN against lease_clauses can produce a NULL confidence for two
  completely different reasons: the topic was never parsed at all (no row
  exists), or the topic was parsed and found not present (clause_text IS NULL,
  confidence is a real value). An awareness item only counts as "not addressed"
  when a lease_clauses row exists AND clause_text IS NULL AND the row is not a
  failed-sentinel row. The get_awareness_items query enforces this via
  lc.confidence IS NOT NULL. Rows failing this check belong in
  processing_warnings["never_parsed"], not in the awareness "not addressed" list.

Trap 2: needs_reparse vs confirmed-absent (both tiers)
  A lease_clauses row with confidence = -1.0 is a placeholder for a Phase 3
  API failure -- the clause match was attempted but never actually judged. It
  must not be treated as a confirmed absence. These rows are surfaced in
  processing_warnings["needs_reparse"] and excluded from awareness items.

Trap 3: compliance_judgment_failed vs genuine needs_review
  compliance_findings rows inserted by compliance_diff.py's batch-failure path
  carry status='needs_review' with an explanation prefixed
  "[AUTOMATED CHECK FAILED]". These are unresolved API failures, not real
  judgment calls. They are excluded from the needs_review count in build_summary
  and from the grouped requirement_findings output, and are surfaced separately
  in processing_warnings["compliance_judgment_failed"].
"""

import json
import sys
from datetime import datetime, timezone
from typing import Any

from api.db import get_connection

# The exact prefix compliance_diff.py uses for batch-failure placeholder rows.
# Findings carrying this prefix are processing failures, not genuine judgments.
_AUTOMATED_FAILURE_PREFIX = "[AUTOMATED CHECK FAILED]"

# Sentinel value from lease_parser.py: a lease_clauses row with this confidence
# was never actually judged -- the Phase 3 API call failed. Cannot appear as
# real LLM output because _validate_classification clamps all real values to
# [0, 1].
_FAILED_CONFIDENCE_SENTINEL = -1.0


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

FindingRow = dict[str, Any]    # one row from get_requirement_findings
AwarenessRow = dict[str, Any]  # one row from get_awareness_items


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_requirement_findings(conn, lease_id: str) -> list[FindingRow]:
    """Join compliance_findings to legal_sources for requirement-tier rows.

    Returns all compliance_findings rows for this lease_id where the
    corresponding legal_sources row is active and check_tier='requirement'.
    Augments each finding with citation, family_key, and jurisdiction from
    legal_sources, and verifier_confirmed / verifier_note from
    compliance_findings.

    Note: this list will legitimately contain FEWER rows than the total number
    of active requirement-tier keys whenever compliance_diff.py categorised some
    as 'missing' (never parsed) or 'needs_reparse' (Phase 3 API failure) --
    those categories never receive a compliance_findings row. That gap is
    correct and expected; it is surfaced via get_processing_warnings, not
    silently absorbed here.

    Parameters
    ----------
    conn:
        An open psycopg connection obtained via ``get_connection()``.
    lease_id:
        UUID string of the lease to report on.

    Returns
    -------
    list[FindingRow]
        Each dict contains ``requirement_key``, ``citation``, ``family_key``,
        ``jurisdiction``, ``status``, ``explanation``, ``verifier_confirmed``,
        and ``verifier_note``. Ordered by jurisdiction then requirement_key.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                cf.requirement_key,
                ls.citation,
                ls.family_key,
                ls.jurisdiction,
                cf.status,
                cf.explanation,
                cf.verifier_confirmed,
                cf.verifier_note
            FROM compliance_findings cf
            JOIN legal_sources ls
                ON ls.requirement_key = cf.requirement_key
            WHERE cf.lease_id = %(lease_id)s
              AND ls.check_tier = 'requirement'
              AND ls.status = 'active'
            ORDER BY ls.jurisdiction, cf.requirement_key
            """,
            {"lease_id": lease_id},
        )
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]

    return [dict(zip(columns, row)) for row in rows]


def get_awareness_items(conn, lease_id: str) -> list[AwarenessRow]:
    """Query awareness-tier items that were parsed and confirmed not present.

    Left-joins all active awareness-tier rows in legal_sources to lease_clauses
    for this lease_id. An item is included in the output ONLY when all three
    conditions hold:

      (a) lc.confidence IS NOT NULL -- a lease_clauses row actually exists for
          this lease_id. A NULL here means the topic was never parsed at all,
          which is an unresolved processing gap, not a confirmed absence. These
          rows belong in processing_warnings["never_parsed"].
      (b) lc.clause_text IS NULL -- the parser found no matching clause.
      (c) lc.confidence != -1.0 -- the row is not a failed-sentinel placeholder
          (confidence = -1.0 means the Phase 3 API call failed; the match was
          never actually judged). These rows belong in
          processing_warnings["needs_reparse"].

    Parameters
    ----------
    conn:
        An open psycopg connection obtained via ``get_connection()``.
    lease_id:
        UUID string of the lease to report on.

    Returns
    -------
    list[AwarenessRow]
        Each dict contains ``citation``, ``summary``, ``source_url``, and
        ``jurisdiction``. Ordered by jurisdiction then citation.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                ls.citation,
                ls.summary,
                ls.source_url,
                ls.jurisdiction
            FROM legal_sources ls
            LEFT JOIN lease_clauses lc
                ON lc.requirement_key = ls.requirement_key
                AND lc.lease_id = %(lease_id)s
            WHERE ls.check_tier = 'awareness'
              AND ls.status = 'active'
              AND lc.confidence IS NOT NULL
              AND lc.clause_text IS NULL
              AND lc.confidence != %(sentinel)s
            ORDER BY ls.jurisdiction, ls.citation
            """,
            {"lease_id": lease_id, "sentinel": _FAILED_CONFIDENCE_SENTINEL},
        )
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]

    return [dict(zip(columns, row)) for row in rows]


def get_processing_warnings(
    conn,
    lease_id: str,
    compliance_judgment_failed: list[str],
) -> dict[str, list[str]]:
    """Collect all categories of unresolved processing failures for this lease.

    Queries two categories from the database and accepts a third as a
    parameter:

    needs_reparse: requirement_keys (any check_tier) that have a lease_clauses
    row with confidence = -1.0. This sentinel means the Phase 3 parser API
    call failed -- the clause match was never actually judged and must be
    reprocessed before a reliable finding can be made.

    never_parsed: active requirement_keys (any check_tier) with no lease_clauses
    row at all for this lease_id. Discovered via a LEFT JOIN where the join
    produces a NULL confidence. Distinct from "parsed and absent" -- a topic
    in this list was simply never seen by the parser for this lease.

    compliance_judgment_failed: passed in from the caller rather than re-derived
    here. Populated by the _is_processing_failure check in generate_report on
    findings returned by get_requirement_findings.

    All three lists are empty in the normal case. Populated lists must be
    surfaced prominently in the report rather than silently ignored.

    Parameters
    ----------
    conn:
        An open psycopg connection obtained via ``get_connection()``.
    lease_id:
        UUID string of the lease to report on.
    compliance_judgment_failed:
        List of requirement_keys whose compliance_findings explanation starts
        with "[AUTOMATED CHECK FAILED]", meaning compliance_diff.py inserted
        a failure placeholder rather than a real judgment.

    Returns
    -------
    dict with keys ``"needs_reparse"``, ``"never_parsed"``, and
    ``"compliance_judgment_failed"``, each a list of requirement_key strings.
    """
    # needs_reparse: rows that exist but have the failure-sentinel confidence.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT lc.requirement_key
            FROM lease_clauses lc
            JOIN legal_sources ls ON ls.requirement_key = lc.requirement_key
            WHERE lc.lease_id = %(lease_id)s
              AND lc.confidence = %(sentinel)s
              AND ls.status = 'active'
            ORDER BY lc.requirement_key
            """,
            {"lease_id": lease_id, "sentinel": _FAILED_CONFIDENCE_SENTINEL},
        )
        needs_reparse = [row[0] for row in cur.fetchall()]

    # never_parsed: active keys with no lease_clauses row at all for this lease.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ls.requirement_key
            FROM legal_sources ls
            LEFT JOIN lease_clauses lc
                ON lc.requirement_key = ls.requirement_key
                AND lc.lease_id = %(lease_id)s
            WHERE ls.status = 'active'
              AND lc.confidence IS NULL
            ORDER BY ls.requirement_key
            """,
            {"lease_id": lease_id},
        )
        never_parsed = [row[0] for row in cur.fetchall()]

    return {
        "needs_reparse": needs_reparse,
        "never_parsed": never_parsed,
        "compliance_judgment_failed": list(compliance_judgment_failed),
    }


# ---------------------------------------------------------------------------
# Processing-failure detection
# ---------------------------------------------------------------------------

def _is_processing_failure(explanation: str) -> bool:
    """Return True if this finding is a batch-failure placeholder from compliance_diff.

    compliance_diff.py inserts status='needs_review' rows with explanations
    starting with "[AUTOMATED CHECK FAILED]" when the Anthropic API call for a
    batch fails. These rows have status='needs_review' in the database but were
    never actually judged; they must not be counted as genuine needs_review
    findings or included in the grouped report output.

    Parameters
    ----------
    explanation:
        The explanation string from a compliance_findings row.

    Returns
    -------
    bool
        True if the explanation starts with the automated-failure prefix.
    """
    return explanation.startswith(_AUTOMATED_FAILURE_PREFIX)


# ---------------------------------------------------------------------------
# Family labels
# ---------------------------------------------------------------------------

def get_family_labels(conn) -> dict[tuple[str, str], str]:
    """Query all rows from family_labels and return a lookup dict.

    Parameters
    ----------
    conn:
        An open psycopg connection obtained via ``get_connection()``.

    Returns
    -------
    dict[tuple[str, str], str]
        Maps ``(family_key, jurisdiction)`` to ``friendly_title`` for every
        row in the family_labels table.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT family_key, jurisdiction, friendly_title FROM family_labels"
        )
        rows = cur.fetchall()

    return {(row[0], row[1]): row[2] for row in rows}


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def group_findings_by_family(
    findings: list[FindingRow],
    labels: dict[tuple[str, str], str] | None = None,
) -> list[dict]:
    """Group requirement findings by family_key.

    Every finding lands in exactly one group keyed by its family_key. Groups
    are sorted by family_key; findings within each group are sorted by
    requirement_key. Single-item families produce a single-item group -- the
    output shape is uniform regardless of family size.

    Each group includes a ``friendly_title`` sourced from the ``labels`` dict
    via ``(family_key, jurisdiction)``, using the jurisdiction of the group's
    first finding (all findings within one family_key share the same
    jurisdiction in practice). If no label exists for a group, ``friendly_title``
    is set to None and a one-line [INFO] note is printed naming the family_key
    and jurisdiction, so unlabelled families are visible rather than silently
    rendered blank as the corpus grows.

    Parameters
    ----------
    findings:
        List of finding dicts as returned by ``get_requirement_findings``,
        already filtered to exclude processing-failure entries.
    labels:
        Mapping of ``(family_key, jurisdiction)`` to ``friendly_title``, as
        returned by ``get_family_labels``. Defaults to None, treated internally
        as an empty dict, so callers that omit this argument degrade gracefully
        (every group's ``friendly_title`` becomes None) rather than raising a
        missing-argument error.

    Returns
    -------
    list[dict]
        Each element is
        ``{"family_key": str, "friendly_title": str | None, "findings": list[FindingRow]}``,
        ordered by family_key ascending.
    """
    label_map = labels if labels is not None else {}

    groups: dict[str, list[FindingRow]] = {}
    for finding in findings:
        fk = finding["family_key"]
        if fk not in groups:
            groups[fk] = []
        groups[fk].append(finding)

    for key in groups:
        groups[key].sort(key=lambda f: f["requirement_key"])

    result: list[dict] = []
    for fk in sorted(groups):
        group_findings = groups[fk]
        jurisdiction = group_findings[0]["jurisdiction"]
        friendly_title = label_map.get((fk, jurisdiction))
        if friendly_title is None:
            print(
                f"  [INFO] group_findings_by_family: no friendly_title authored "
                f"for family_key='{fk}', jurisdiction='{jurisdiction}'."
            )
        result.append({
            "family_key": fk,
            "friendly_title": friendly_title,
            "findings": group_findings,
        })

    return result


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def build_summary(requirement_findings: list[FindingRow]) -> dict[str, int]:
    """Compute counts over the requirement findings for the report summary.

    Processing-failure findings (where ``_is_processing_failure(explanation)``
    is True) are excluded from both the ``needs_review`` count and the
    ``total`` count -- they are API failures, not real judgments, and are
    tracked separately in ``processing_warnings["compliance_judgment_failed"]``.

    ``disputed_by_verifier`` counts findings where ``verifier_confirmed`` is
    explicitly False (meaning the verifier identified a reasoning inconsistency
    in the compliance-diff agent's output). Findings where ``verifier_confirmed``
    is True or None (never verified) do not contribute to this count.

    Parameters
    ----------
    requirement_findings:
        Full list of findings from ``get_requirement_findings``, including any
        processing-failure entries (they are filtered internally).

    Returns
    -------
    dict with integer keys ``total``, ``compliant``, ``contradicts``,
    ``needs_review``, ``absent``, and ``disputed_by_verifier``.
    """
    counts: dict[str, int] = {
        "total": 0,
        "compliant": 0,
        "contradicts": 0,
        "needs_review": 0,
        "absent": 0,
        "disputed_by_verifier": 0,
    }

    for f in requirement_findings:
        if _is_processing_failure(f["explanation"]):
            # Processing failures are tracked in processing_warnings, not here.
            continue

        counts["total"] += 1
        status = f["status"]
        if status in counts:
            counts[status] += 1

        if f["verifier_confirmed"] is False:
            counts["disputed_by_verifier"] += 1

    return counts


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def generate_report(lease_id: str) -> dict[str, Any]:
    """Assemble the full compliance report for a lease from already-computed results.

    Orchestrates all queries and transformations. No LLM calls are made.

    The verifier_flag field added to each finding within requirement_findings
    groups uses the following tri-state logic:
      - verifier_confirmed is False: verifier_flag = the verifier_note text
        (passed through verbatim -- the verifier's note is already concise).
      - verifier_confirmed is True: verifier_flag = null. The verdict was
        confirmed; nothing needs flagging.
      - verifier_confirmed is None (finding was never sent for verification):
        verifier_flag = null. Both True and None render as "nothing to flag" --
        they must not be confused with each other, but both produce a null flag
        in the output since neither represents a raised concern.

    Parameters
    ----------
    lease_id:
        UUID string of the lease to report on.

    Returns
    -------
    dict
        Full report structure: lease_id, generated_at (ISO 8601 UTC),
        summary, requirement_findings (grouped with friendly_title per group,
        processing failures excluded), awareness_items, processing_warnings,
        and disclaimer. Each group's ``friendly_title`` is str | None -- None
        when no label has been authored for that family_key/jurisdiction pair,
        which also triggers an [INFO] log line so gaps are visible.
    """
    conn = get_connection()
    try:
        all_findings = get_requirement_findings(conn, lease_id)
        awareness_items = get_awareness_items(conn, lease_id)
        family_labels = get_family_labels(conn)

        # Split findings into normal and processing-failure sets before any
        # further processing. The failure set feeds processing_warnings only.
        normal_findings: list[FindingRow] = []
        failed_keys: list[str] = []
        for f in all_findings:
            if _is_processing_failure(f["explanation"]):
                failed_keys.append(f["requirement_key"])
            else:
                normal_findings.append(f)

        summary = build_summary(all_findings)
        processing_warnings = get_processing_warnings(conn, lease_id, failed_keys)
    finally:
        conn.close()

    # Group normal findings by family and attach the verifier_flag per finding.
    # family_labels was fetched inside the try block above, before conn.close().
    grouped = group_findings_by_family(normal_findings, labels=family_labels)
    for group in grouped:
        enriched: list[dict] = []
        for f in group["findings"]:
            # verifier_confirmed=False → pass note through verbatim.
            # verifier_confirmed=True or None → null in both cases (confirmed
            # verdict and never-verified verdict both render as no flag raised).
            if f["verifier_confirmed"] is False:
                verifier_flag = f["verifier_note"]
            else:
                verifier_flag = None

            enriched.append({
                "requirement_key": f["requirement_key"],
                "citation": f["citation"],
                "jurisdiction": f["jurisdiction"],
                "status": f["status"],
                "explanation": f["explanation"],
                "verifier_confirmed": f["verifier_confirmed"],
                "verifier_flag": verifier_flag,
            })
        group["findings"] = enriched

    return {
        "lease_id": lease_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "requirement_findings": grouped,
        "awareness_items": awareness_items,
        "processing_warnings": processing_warnings,
        "disclaimer": (
            "This report is a compliance checklist based on Pittsburgh-area "
            "landlord-tenant law. It is not legal advice and does not create an "
            "attorney-client relationship. Consult a licensed attorney before "
            "making legal decisions based on these findings."
        ),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python agents/report_builder.py <lease_id>")
        sys.exit(1)

    report = generate_report(sys.argv[1])
    print(json.dumps(report, indent=2, default=str))
