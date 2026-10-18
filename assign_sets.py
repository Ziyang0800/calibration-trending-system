"""
assign_sets.py - applies a {serial: set_id} mapping to the database directly.

Edit the MAPPING dict below with your serial -> Set assignments, then run:
    python assign_sets.py --db calibration.db

Prints which serials were updated and which weren't found (typo, or not
migrated into the database yet) so nothing silently fails.
"""

import argparse

from db import connect, bulk_assign_sets

# Fill this in with your actual serial -> Set mapping.
MAPPING = {
     "1692418": "Set 1",
     "74076": "Set 2",
     "73137": "Set 3",
     "7575009": "Set 1",
     "7575006": "Set 2",
     "7475004": "Set 1",
     "7651002": "Set 2",
     "7611001": "Set 1",
     "7678001": "Set 2",
     "7601001": "Set 1",
     "7601005": "Set 2",
     "834041": "Set 1",
     "834024": "Set 2",
     "7630001": "Set 1",
     "7630002": "Set 2",
     "7597003": "Set 1",
     "7565005": "Set 2",
     "7510007": "Set 1",
     "7540002": "Set 2",
     "63438": "Set 1",
     "63433": "Set 2",
     "71145": "Set 1",
     "68820": "Set 2",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="calibration.db")
    args = ap.parse_args()

    if not MAPPING:
        print("MAPPING is empty - edit assign_sets.py and fill in your serial -> Set assignments first.")
        return

    conn = connect(args.db)
    result = bulk_assign_sets(conn, MAPPING)
    conn.close()

    print(f"Updated {len(result['updated'])} asset(s): {result['updated']}")
    if result["not_found"]:
        print(f"NOT FOUND (check for typos, or these serials aren't migrated yet): {result['not_found']}")


if __name__ == "__main__":
    main()
