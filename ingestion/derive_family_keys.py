"""
Derives family_key for every row in legal_sources, grouping subsections of
the same statutory/ordinance section together (e.g. 511.1(a), 511.1(b), and
511.1(c) all get family_key '511.1'). This lets compliance_diff.py show a
requirement's modifying or related subsections alongside its own full_text
without a hand-curated relationship list -- see decisions.md for the full
reasoning on why this is derived mechanically rather than maintained by hand.

The extraction pattern was verified against every citation format actually
present across all four jurisdictions before being written here (PA state
statute decimal notation, Allegheny County letter-suffixed subsections,
Pittsburgh's own decimal ordinance numbering, and federal U.S. Code section
numbers that can end in a letter as part of the base number, e.g. "4852d").

Run this after loading new legal_sources data, or re-run any time citation
text changes -- it's idempotent, always recomputing from the current
citation string rather than accumulating stale values.
"""
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from api.db import get_connection

# Matches "Section X" / "Sections X" / "§ X", capturing the section number
# itself: digits, an optional decimal subsection (511.1), an optional
# hyphenated letter suffix (502-A), or an optional directly-attached letter
# (4852d). Stops before a parenthetical subsection like "(a)" or "(b)-(c)".
_FAMILY_KEY_PATTERN = re.compile(r"(?:Section|§)s?\s+(\d+(?:\.\d+)?(?:-[A-Za-z])?[A-Za-z]?)")


def derive_family_key(citation: str) -> str | None:
    """Extract a family_key from a citation string.

    Parameters
    ----------
    citation:
        The full citation string, e.g. "68 P.S. Section 511.1(a)".

    Returns
    -------
    str or None
        The derived family key (e.g. "511.1"), or None if no section number
        could be found in the citation at all.
    """
    match = _FAMILY_KEY_PATTERN.search(citation)
    return match.group(1) if match else None


def populate_family_keys(conn) -> None:
    """Derive and write family_key for every row in legal_sources.

    Prints each row's citation alongside its derived family_key as it goes,
    so the mapping can be visually spot-checked in the terminal output
    immediately, the same review discipline used throughout this project's
    data sourcing.

    Parameters
    ----------
    conn:
        An open psycopg connection obtained via ``get_connection()``.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id, requirement_key, citation FROM legal_sources ORDER BY id")
        rows = cur.fetchall()

    updated = 0
    unmatched: list[str] = []

    with conn.cursor() as cur:
        for row_id, requirement_key, citation in rows:
            family_key = derive_family_key(citation)
            print(f"  {citation:70s} -> {family_key}")

            if family_key is None:
                unmatched.append(requirement_key)
                continue

            cur.execute(
                "UPDATE legal_sources SET family_key = %s WHERE id = %s",
                (family_key, row_id),
            )
            updated += 1

    print(f"\nUpdated {updated}/{len(rows)} rows with a derived family_key.")
    if unmatched:
        print(
            f"[WARN] {len(unmatched)} rows had no extractable section number "
            f"and were left with family_key = NULL: {', '.join(unmatched)}"
        )


if __name__ == "__main__":
    conn = get_connection()
    try:
        populate_family_keys(conn)
    finally:
        conn.close()
