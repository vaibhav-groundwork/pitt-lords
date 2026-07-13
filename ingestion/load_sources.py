"""
Loads hand-sourced legal requirement files (see data/*.json) into the
legal_sources table, computing an embedding for each row along the way.

Usage:
    python ingestion/load_sources.py data/pa_security_deposits.json
    python ingestion/load_sources.py data/pa_security_deposits.json data/pa_written_lease.json
    python ingestion/load_sources.py data/*.json
"""
import glob
import json
import sys
from pathlib import Path

from sentence_transformers import SentenceTransformer

sys.path.append(str(Path(__file__).resolve().parent.parent))
from api.db import get_connection

# Same embedding model Groundwork used: small, runs locally, no API cost.
# Loading it once at module level means it's only loaded into memory once
# per script run, not once per row.
MODEL = SentenceTransformer("all-MiniLM-L6-v2")


def embed(text: str) -> list[float]:
    """
    Turns a chunk of text into a 384-number vector that captures its meaning.
    Two chunks about similar topics end up as vectors that are close together
    in this 384-dimensional space -- that's what lets the compliance-diff
    agent later find "which requirement is this lease clause talking about"
    using math (vector distance) instead of just keyword matching.
    """
    return MODEL.encode(text).tolist()


def load_file(path: str):
    with open(path) as f:
        rows = json.load(f)

    conn = get_connection()
    inserted = 0

    with conn.cursor() as cur:
        for row in rows:
            # We embed the summary, not the full legal text. The summary is
            # what a lease clause's plain-language content will be compared
            # against -- embedding the dense statutory language directly
            # tends to produce noisier matches than embedding a clean
            # plain-language description of what the rule requires.
            vector = embed(row["summary"])

            # check_tier defaults to "requirement" so existing JSON files
            # that predate this field don't need to be rewritten. Set it
            # explicitly to "awareness" in a file for background items that
            # don't map to a specific checkable lease clause.
            check_tier = row.get("check_tier", "requirement")

            cur.execute(
                """
                INSERT INTO legal_sources
                    (jurisdiction, citation, requirement_key, summary,
                     full_text, source_url, retrieved_on,
                     source_currency_date, status, check_tier, embedding)
                VALUES (%(jurisdiction)s, %(citation)s, %(requirement_key)s,
                        %(summary)s, %(full_text)s, %(source_url)s,
                        %(retrieved_on)s, %(source_currency_date)s,
                        %(status)s, %(check_tier)s, %(vector)s)
                """,
                {**row, "vector": vector, "check_tier": check_tier},
            )
            inserted += 1
            print(f"  inserted {row['requirement_key']}")

    conn.close()
    print(f"Done. Inserted {inserted} rows from {path}.")
    return inserted


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ingestion/load_sources.py <file1.json> [file2.json ...]")
        print("       python ingestion/load_sources.py data/*.json")
        sys.exit(1)

    # The shell expands data/*.json into a list of paths automatically, so
    # this loop handles one file, several files, or a wildcard glob the same
    # way, one clean run instead of six separate commands.
    total = 0
    for path in sys.argv[1:]:
        total += load_file(path)
    print(f"\nAll files done. Inserted {total} rows total across {len(sys.argv) - 1} file(s).")
