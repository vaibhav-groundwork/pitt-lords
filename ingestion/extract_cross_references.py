"""
Automatically extracts explicit cross-family citation references from
legal_sources.full_text, populating family_cross_references. This is the
scalable alternative to a hand-curated relationship list: our full_text is
primary-source legal language we sourced ourselves, and it already contains
explicit citation phrases (e.g. "in accordance with sections 511.2 and
512", "termination due to the provisions of section 505-A") whenever one
provision genuinely depends on another. Rather than re-reading the corpus
by hand to find these, this script parses them out mechanically -- so it
scales to a much larger corpus later without more manual review, and it
naturally stays in sync if full_text is ever revised.

Only creates a reference when the target family_key actually exists within
the SAME jurisdiction as the source row -- a mention of an unsourced law
(e.g. a citation to a different statute title entirely) is intentionally
discarded rather than creating a dangling reference to nothing.

Run this after populating family_key via derive_family_keys.py, and re-run
any time full_text changes or new rows are added -- it is idempotent
(ON CONFLICT DO NOTHING on the unique constraint).
"""
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from api.db import get_connection

# Captures a "Section X[, Y and Z]" style list, case-insensitive since real
# statutory prose mixes "Section 505-A" (capitalized, start of a citation)
# with "in accordance with sections 511.2 and 512" (lowercase, mid-sentence).
_REFERENCE_LIST_PATTERN = re.compile(
    r"(?:Sections?|§)\s+"
    r"(\d+(?:\.\d+)?(?:-[A-Za-z])?[A-Za-z]?"
    r"(?:\s*(?:,|and|or)\s*\d+(?:\.\d+)?(?:-[A-Za-z])?[A-Za-z]?)*)",
    re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?(?:-[A-Za-z])?[A-Za-z]?")


def extract_referenced_families(full_text: str) -> set[str]:
    """Extract every distinct family_key-shaped section reference mentioned in text.

    Parameters
    ----------
    full_text:
        The statutory/ordinance full_text to scan.

    Returns
    -------
    set[str]
        Deduplicated set of section-number-shaped strings found (e.g.
        {"511.2", "512"}). Callers must still check these against known
        family_keys in the same jurisdiction before treating them as real.
    """
    found: set[str] = set()
    for match in _REFERENCE_LIST_PATTERN.finditer(full_text):
        for number in _NUMBER_PATTERN.findall(match.group(1)):
            found.add(number)
    return found


def populate_cross_references(conn) -> None:
    """Scan every legal_sources row's full_text and populate family_cross_references.

    For each row, extracts referenced section numbers from its own full_text,
    excludes a self-reference to its own family_key, checks whether each
    remaining reference matches a real family_key present in the same
    jurisdiction, and inserts a (source_family_key, target_family_key,
    jurisdiction) row for each real match found. Prints progress and flags
    any referenced-but-unresolved numbers for visual review.

    Parameters
    ----------
    conn:
        An open psycopg connection obtained via ``get_connection()``.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT requirement_key, jurisdiction, family_key, full_text "
            "FROM legal_sources WHERE family_key IS NOT NULL"
        )
        rows = cur.fetchall()

        # Build a lookup of which family_keys actually exist per jurisdiction,
        # so a referenced number only becomes a real cross-reference if we
        # actually sourced that section ourselves.
        cur.execute(
            "SELECT DISTINCT jurisdiction, family_key FROM legal_sources "
            "WHERE family_key IS NOT NULL"
        )
        known_families: dict[str, set[str]] = {}
        for jurisdiction, family_key in cur.fetchall():
            known_families.setdefault(jurisdiction, set()).add(family_key)

    inserted = 0
    unresolved: list[str] = []

    with conn.cursor() as cur:
        for requirement_key, jurisdiction, family_key, full_text in rows:
            referenced = extract_referenced_families(full_text)
            referenced.discard(family_key)  # exclude self-references

            for target in referenced:
                if target in known_families.get(jurisdiction, set()):
                    cur.execute(
                        """
                        INSERT INTO family_cross_references
                            (source_family_key, target_family_key, jurisdiction)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (source_family_key, target_family_key, jurisdiction)
                        DO NOTHING
                        """,
                        (family_key, target, jurisdiction),
                    )
                    print(
                        f"  [{jurisdiction}] {requirement_key} ({family_key}) "
                        f"-> {target}"
                    )
                    inserted += 1
                else:
                    unresolved.append(
                        f"{requirement_key} references '{target}', not in our corpus"
                    )

    print(f"\nInserted {inserted} cross-family references (duplicates skipped).")
    if unresolved:
        print(
            f"\n[INFO] {len(unresolved)} referenced sections were not found in "
            "our sourced corpus (likely references to unsourced law, e.g. a "
            "different statute title entirely) -- correctly discarded:"
        )
        for u in unresolved:
            print(f"    {u}")


if __name__ == "__main__":
    conn = get_connection()
    try:
        populate_cross_references(conn)
    finally:
        conn.close()
