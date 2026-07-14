"""
Loads data/family_labels.json into the family_labels table.

These titles are hand-authored (not derived or inferred) -- see the JSON
file itself for the actual text. This script only handles insertion.
Idempotent: uses ON CONFLICT DO UPDATE so re-running after editing the
JSON file cleanly applies changes rather than erroring on duplicate keys.

Run after any edit to data/family_labels.json:
    python ingestion/load_family_labels.py
"""
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from api.db import get_connection

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "family_labels.json"


def load_family_labels(conn) -> int:
    """Insert or update every entry in data/family_labels.json.

    Parameters
    ----------
    conn:
        An open psycopg connection obtained via ``get_connection()``.

    Returns
    -------
    int
        Number of rows inserted or updated.
    """
    with open(_DATA_FILE) as f:
        entries = json.load(f)

    with conn.cursor() as cur:
        for entry in entries:
            cur.execute(
                """
                INSERT INTO family_labels (family_key, jurisdiction, friendly_title)
                VALUES (%(family_key)s, %(jurisdiction)s, %(friendly_title)s)
                ON CONFLICT (family_key, jurisdiction)
                DO UPDATE SET friendly_title = EXCLUDED.friendly_title
                """,
                entry,
            )
            print(f"  [{entry['jurisdiction']}] {entry['family_key']} -> {entry['friendly_title']}")

    return len(entries)


if __name__ == "__main__":
    conn = get_connection()
    try:
        count = load_family_labels(conn)
        print(f"\nLoaded {count} family labels.")
    finally:
        conn.close()
