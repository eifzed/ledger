#!/usr/bin/env python3
"""One-time migration: shift all stored timestamps from Jakarta (UTC+7) to UTC.

Previously the app stored naive datetimes using now_jakarta(), so the raw values
in SQLite represent Jakarta local time.  After the UTC-storage change, the app
reads them as UTC, causing a +7 hour shift.

This script subtracts 7 hours from every datetime column to correct that.

Usage:
    python scripts/migrate_to_utc.py              # uses default ./data/ledger.db
    python scripts/migrate_to_utc.py /path/to.db  # explicit path

A backup is created automatically before any changes (*.pre-utc-migration.bak).
"""

import shutil
import sqlite3
import sys
from pathlib import Path

OFFSET = "-7 hours"

COLUMNS_TO_MIGRATE = [
    ("transactions", "effective_at"),
    ("transactions", "created_at"),
    ("users", "created_at"),
    ("accounts", "created_at"),
    ("budgets", "created_at"),
    ("budgets", "updated_at"),
    ("budget_snapshots", "created_at"),
]


def migrate(db_path: str) -> None:
    path = Path(db_path)
    if not path.exists():
        print(f"Database not found: {path}")
        sys.exit(1)

    backup = path.with_suffix(".pre-utc-migration.bak")
    print(f"Backing up  {path}  →  {backup}")
    shutil.copy2(path, backup)

    conn = sqlite3.connect(str(path))
    cur = conn.cursor()

    total_affected = 0
    for table, column in COLUMNS_TO_MIGRATE:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL")
        count = cur.fetchone()[0]
        if count == 0:
            print(f"  {table}.{column:15s}  — no rows, skipped")
            continue

        cur.execute(
            f"UPDATE {table} SET {column} = datetime({column}, ?) WHERE {column} IS NOT NULL",
            (OFFSET,),
        )
        affected = cur.rowcount
        total_affected += affected
        print(f"  {table}.{column:15s}  — {affected} rows shifted by {OFFSET}")

    conn.commit()
    conn.close()

    print(f"\nDone. {total_affected} total values migrated to UTC.")
    print(f"Backup saved at: {backup}")


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "./data/ledger.db"
    migrate(db)
