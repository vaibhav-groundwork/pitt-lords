"""
Eval suite scoring script -- Phase 6.

Runs every synthetic test lease in eval/test_leases/ through the full pipeline
(document_extract -> lease_parser -> compliance_diff -> optionally verifier),
scores the compliance_findings against the expected outcomes in
eval/ground_truth.json, and prints a categorised report.

Deterministic lease IDs
------------------------
Each test filename is mapped to a stable UUID via
``uuid.uuid5(uuid.NAMESPACE_DNS, filename)`` rather than a random UUID.
This means rerunning the eval suite overwrites the same lease's prior results
each time -- lease_parser.parse_lease and compliance_diff.run_compliance_diff
are already idempotent per lease_id (they delete prior rows before writing),
so a stable ID gives clean re-runs without accumulating orphaned rows in the
database under a new random ID on every invocation.

Connection handling
--------------------
agents/lease_parser.parse_lease, agents/compliance_diff.run_compliance_diff,
and agents/verifier.run_verifier each open and close their own internal
connections. run_eval() opens one additional connection exclusively for
querying results (get_actual_findings), held open across all leases and
closed in a finally block at the end of run_eval(), not per-lease.

Scoring categories
-------------------
  CORRECT       -- actual status matches ground truth
  DANGEROUS     -- a real issue (contradicts / absent / non-compliant list)
                   was expected, but the pipeline returned 'compliant'
  CONSERVATIVE  -- expected 'compliant' but pipeline returned 'needs_review'
                   (acceptable direction to err; not a failure)
  WRONG_OTHER   -- incorrect answer not covered by the above two cases
  MISSING       -- requirement_key in ground truth has no row at all in
                   compliance_findings (pipeline gap, not a scoring disagreement)

Exit code is non-zero if any DANGEROUS findings exist, enabling use as a
pass/fail gate in a CI step.
"""

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from agents.document_extract import extract_text
from agents.lease_parser import parse_lease
from agents.compliance_diff import run_compliance_diff
from api.db import get_connection

# Ground truth and test lease directories are co-located with this script.
_EVAL_DIR = Path(__file__).parent
_GROUND_TRUTH_PATH = _EVAL_DIR / "ground_truth.json"
_TEST_LEASES_DIR = _EVAL_DIR / "test_leases"

# Scoring category constants -- used as dict values and in report headers.
_CORRECT = "CORRECT"
_DANGEROUS = "DANGEROUS"
_CONSERVATIVE = "CONSERVATIVE"
_WRONG_OTHER = "WRONG_OTHER"
_MISSING = "MISSING"


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

GroundTruth = dict[str, Any]          # full ground_truth.json structure
ExpectedValue = str | list[str]       # single status string or list of acceptable ones
ResultRow = dict[str, Any]            # one scored expectation


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_ground_truth() -> GroundTruth:
    """Load and parse eval/ground_truth.json.

    Returns
    -------
    dict
        The full parsed ground truth, keyed by filename.

    Raises
    ------
    FileNotFoundError
        If eval/ground_truth.json does not exist.
    """
    with open(_GROUND_TRUTH_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline_for_lease(
    filename: str,
    lease_id: str,
    run_verifier_too: bool = False,
) -> None:
    """Run the full pipeline for one test lease file.

    Stages: extract_text -> parse_lease -> run_compliance_diff ->
    (optionally) run_verifier. Each stage that raises is caught and reported
    clearly by name; after a failure the function returns without raising so
    the rest of the eval suite continues.

    Parameters
    ----------
    filename:
        Basename of the .docx file inside eval/test_leases/.
    lease_id:
        Deterministic UUID string derived from the filename. Passed explicitly
        to parse_lease so the same ID is reused on reruns (idempotency).
    run_verifier_too:
        Whether to also run agents.verifier.run_verifier after compliance_diff.
    """
    file_path = _TEST_LEASES_DIR / filename
    print(f"\n{'─' * 60}")
    print(f"Processing: {filename}  (lease_id={lease_id})")
    print(f"{'─' * 60}")

    try:
        text = extract_text(str(file_path))
    except Exception as exc:
        print(f"  [ERROR] {filename}: extract_text failed -- {exc}")
        return

    try:
        parse_lease(text, lease_id=lease_id)
    except Exception as exc:
        print(f"  [ERROR] {filename}: parse_lease failed -- {exc}")
        return

    try:
        run_compliance_diff(lease_id)
    except Exception as exc:
        print(f"  [ERROR] {filename}: run_compliance_diff failed -- {exc}")
        return

    if run_verifier_too:
        try:
            from agents.verifier import run_verifier
            run_verifier(lease_id)
        except Exception as exc:
            print(f"  [ERROR] {filename}: run_verifier failed -- {exc}")
            # Verifier failure does not stop scoring -- findings still exist.


# ---------------------------------------------------------------------------
# Result querying
# ---------------------------------------------------------------------------

def get_actual_findings(conn, lease_id: str) -> dict[str, dict]:
    """Query compliance_findings for this lease_id.

    Parameters
    ----------
    conn:
        The eval suite's own open psycopg connection (held across all leases).
    lease_id:
        UUID string identifying the lease.

    Returns
    -------
    dict[str, dict]
        Maps requirement_key -> {"status": ..., "verifier_confirmed": ...,
        "verifier_note": ...}. verifier fields are None if the verifier was
        not run or the field was left NULL.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT requirement_key, status, verifier_confirmed, verifier_note
            FROM compliance_findings
            WHERE lease_id = %s
            """,
            (lease_id,),
        )
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]

    return {
        row_dict["requirement_key"]: row_dict
        for row_dict in (dict(zip(columns, row)) for row in rows)
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _is_correct(expected: ExpectedValue, actual_status: str) -> bool:
    """Return True if actual_status satisfies the expected value."""
    if isinstance(expected, list):
        return actual_status in expected
    return actual_status == expected


def _signals_real_issue(expected: ExpectedValue) -> bool:
    """Return True if the expected value represents a real compliance issue.

    A "real issue" means the ground truth requires the pipeline to flag
    something -- so returning 'compliant' would be a dangerous miss.

    Conditions:
      - expected == "contradicts" (an explicit violation was expected)
      - expected == "absent" (the requirement is absent; calling it compliant
        means we falsely reported coverage that isn't there)
      - expected is a list that does not include "compliant" (even the lenient
        acceptable set still requires some kind of flag)
    """
    if isinstance(expected, list):
        return "compliant" not in expected
    return expected in ("contradicts", "absent")


def score_lease(
    filename: str,
    expected: dict[str, ExpectedValue],
    actual: dict[str, dict],
) -> list[ResultRow]:
    """Score one lease's findings against its ground-truth expectations.

    Ground truth is the driver: every requirement_key in ``expected`` produces
    exactly one result row, regardless of whether it appears in ``actual``.
    Keys in ``actual`` that are not in ``expected`` are ignored.

    Parameters
    ----------
    filename:
        Used to label result rows for reporting.
    expected:
        Dict of {requirement_key: expected_value} from ground_truth.json.
    actual:
        Dict from ``get_actual_findings``.

    Returns
    -------
    list[ResultRow]
        One dict per expected requirement_key, each containing ``filename``,
        ``requirement_key``, ``expected``, ``actual_status``,
        ``verifier_confirmed``, ``verifier_note``, and ``category``.
    """
    results: list[ResultRow] = []

    for req_key, exp_value in expected.items():
        actual_row = actual.get(req_key)

        if actual_row is None:
            results.append({
                "filename": filename,
                "requirement_key": req_key,
                "expected": exp_value,
                "actual_status": "NO_FINDING_PRODUCED",
                "verifier_confirmed": None,
                "verifier_note": None,
                "category": _MISSING,
            })
            continue

        actual_status = actual_row["status"]
        verifier_confirmed = actual_row.get("verifier_confirmed")
        verifier_note = actual_row.get("verifier_note")

        if _is_correct(exp_value, actual_status):
            category = _CORRECT
        elif _signals_real_issue(exp_value) and actual_status == "compliant":
            category = _DANGEROUS
        elif exp_value == "compliant" and actual_status == "needs_review":
            category = _CONSERVATIVE
        else:
            category = _WRONG_OTHER

        results.append({
            "filename": filename,
            "requirement_key": req_key,
            "expected": exp_value,
            "actual_status": actual_status,
            "verifier_confirmed": verifier_confirmed,
            "verifier_note": verifier_note,
            "category": category,
        })

    return results


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_eval(
    lease_filenames: list[str] | None = None,
    run_verifier_too: bool = False,
) -> list[ResultRow]:
    """Run the eval suite across all (or a subset of) test leases.

    Parameters
    ----------
    lease_filenames:
        Filenames to evaluate. If None, uses every filename in ground_truth.json.
    run_verifier_too:
        Whether to run agents.verifier.run_verifier after each compliance_diff.

    Returns
    -------
    list[ResultRow]
        Flat list of scored result rows across all leases.
    """
    ground_truth = load_ground_truth()

    if lease_filenames is None:
        lease_filenames = list(ground_truth.keys())

    all_results: list[ResultRow] = []
    conn = get_connection()

    try:
        for filename in lease_filenames:
            if filename not in ground_truth:
                print(f"  [WARN] {filename} not found in ground_truth.json -- skipping.")
                continue

            # Stable UUID: same filename always maps to the same lease_id.
            lease_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, filename))

            run_pipeline_for_lease(filename, lease_id, run_verifier_too=run_verifier_too)

            actual = get_actual_findings(conn, lease_id)
            expected = ground_truth[filename]["expected"]
            results = score_lease(filename, expected, actual)
            all_results.extend(results)

            # Per-lease summary.
            counts = {_CORRECT: 0, _DANGEROUS: 0, _CONSERVATIVE: 0,
                      _WRONG_OTHER: 0, _MISSING: 0}
            for r in results:
                counts[r["category"]] += 1
            print(
                f"\n  Score for {filename}: "
                f"correct={counts[_CORRECT]}  "
                f"dangerous={counts[_DANGEROUS]}  "
                f"conservative={counts[_CONSERVATIVE]}  "
                f"wrong_other={counts[_WRONG_OTHER]}  "
                f"missing={counts[_MISSING]}"
            )

    finally:
        conn.close()

    return all_results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_final_report(all_results: list[ResultRow], run_verifier_too: bool) -> None:
    """Print the full categorised eval report to stdout.

    Parameters
    ----------
    all_results:
        Flat list of result rows from ``run_eval``.
    run_verifier_too:
        If True, appends a verifier-effectiveness section for DANGEROUS and
        WRONG_OTHER findings.
    """
    total = len(all_results)
    by_category: dict[str, list[ResultRow]] = {
        _CORRECT: [], _DANGEROUS: [], _CONSERVATIVE: [],
        _WRONG_OTHER: [], _MISSING: [],
    }
    for r in all_results:
        by_category[r["category"]].append(r)

    correct_count = len(by_category[_CORRECT])
    pct = (correct_count / total * 100) if total else 0.0

    print(f"\n{'=' * 70}")
    print("EVAL SUITE FINAL REPORT")
    print(f"{'=' * 70}")

    # (1) Overall.
    print(f"\nTotal expectations scored: {total}")
    print(f"Correct:                   {correct_count} / {total}  ({pct:.1f}%)")

    # (2) DANGEROUS -- most important, visually distinct.
    dangerous = by_category[_DANGEROUS]
    print(f"\n{'!' * 70}")
    print(f"!!! DANGEROUS ({len(dangerous)}) -- real issue called 'compliant'")
    print(f"{'!' * 70}")
    if dangerous:
        for r in dangerous:
            exp_display = (
                "/".join(r["expected"])
                if isinstance(r["expected"], list)
                else r["expected"]
            )
            print(
                f"  {r['filename']}  |  {r['requirement_key']}"
                f"  |  expected={exp_display}  |  actual={r['actual_status']}"
            )
    else:
        print("  (none -- pipeline passed all safety-critical checks)")

    # (3) CONSERVATIVE -- just a count.
    conservative = by_category[_CONSERVATIVE]
    print(f"\nConservative (needs_review on a clean case): {len(conservative)}")

    # (4) WRONG_OTHER -- listed for manual review.
    wrong_other = by_category[_WRONG_OTHER]
    print(f"\nWrong (other) ({len(wrong_other)}) -- incorrect, not dangerous:")
    if wrong_other:
        for r in wrong_other:
            exp_display = (
                "/".join(r["expected"])
                if isinstance(r["expected"], list)
                else r["expected"]
            )
            print(
                f"  {r['filename']}  |  {r['requirement_key']}"
                f"  |  expected={exp_display}  |  actual={r['actual_status']}"
            )
    else:
        print("  (none)")

    # (5) MISSING -- pipeline gaps, not scoring disagreements.
    missing = by_category[_MISSING]
    print(f"\nMissing ({len(missing)}) -- no compliance_findings row produced:")
    if missing:
        for r in missing:
            print(f"  {r['filename']}  |  {r['requirement_key']}")
    else:
        print("  (none)")

    # (6) Verifier effectiveness section (only when verifier was run).
    if run_verifier_too:
        flagged = by_category[_DANGEROUS] + by_category[_WRONG_OTHER]
        print(f"\n{'─' * 70}")
        print("VERIFIER EFFECTIVENESS (DANGEROUS + WRONG_OTHER findings)")
        print(f"{'─' * 70}")

        if not flagged:
            print("  No DANGEROUS or WRONG_OTHER findings to check.")
        else:
            caught = 0
            missed = 0
            for r in flagged:
                exp_display = (
                    "/".join(r["expected"])
                    if isinstance(r["expected"], list)
                    else r["expected"]
                )
                vc = r["verifier_confirmed"]
                vc_label = (
                    "CAUGHT (verifier_confirmed=false)"
                    if vc is False
                    else f"missed (verifier_confirmed={vc})"
                )
                if vc is False:
                    caught += 1
                else:
                    missed += 1
                print(
                    f"  [{r['category']}] {r['filename']}  |  "
                    f"{r['requirement_key']}  |  expected={exp_display}  |  "
                    f"actual={r['actual_status']}  |  {vc_label}"
                )
            print(
                f"\n  Verifier caught:  {caught} / {len(flagged)} errors  "
                f"({caught / len(flagged) * 100:.1f}%)"
            )
            print(
                f"  Verifier missed:  {missed} / {len(flagged)} errors  "
                f"({missed / len(flagged) * 100:.1f}%)"
            )

    print(f"\n{'=' * 70}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the Pitt-Lords eval suite against synthetic test leases."
    )
    parser.add_argument(
        "--with-verifier",
        action="store_true",
        help="Also run agents.verifier after each compliance_diff and include "
             "verifier-effectiveness metrics in the report.",
    )
    args = parser.parse_args()

    ground_truth = load_ground_truth()
    all_results = run_eval(run_verifier_too=args.with_verifier)
    print_final_report(all_results, run_verifier_too=args.with_verifier)

    dangerous_count = sum(1 for r in all_results if r["category"] == _DANGEROUS)
    if dangerous_count > 0:
        sys.exit(1)
