"""Verify migration results in migration_audit_transcripts_and_covers.csv
and generate rollback SQL statements.

Produces two files in the backend/ directory:
 - migration_verification.csv  : table,id,column,after,r2_exists,notes
 - migration_rollback.sql      : SQL BEGIN/UPDATE/COMMIT statements

This script expects to be run from the `backend/` directory and that
the environment contains R2 credentials (use run_with_env.ps1 to set them).
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent
AUDIT_CSV = ROOT / "migration_audit_transcripts_and_covers.csv"
VERIFY_CSV = ROOT / "migration_verification.csv"
ROLLBACK_SQL = ROOT / "migration_rollback.sql"


def parse_r2_path(r2path: str):
    # Accept formats r2://bucket/key or bucket/key
    if not r2path:
        return None, None
    if r2path.startswith("r2://"):
        p = r2path[5:]
    else:
        p = r2path
    parts = p.split("/", 1)
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]


def quote_sql(value: str) -> str:
    # If empty string, we'll return NULL token; else return single-quoted and escaped
    if value is None:
        return "NULL"
    if value == "":
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def main() -> int:
    if not AUDIT_CSV.exists():
        print(f"Missing audit CSV at {AUDIT_CSV}")
        return 2

    # Import r2 helper dynamically
    try:
        # Ensure backend is on path so 'infrastructure' package is importable
        sys.path.insert(0, str(ROOT))
        from infrastructure import r2
    except Exception as e:
        print(f"Failed to import R2 helper: {e}")
        return 3

    rows = []
    with AUDIT_CSV.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(r)

    verify_rows: List[dict] = []
    rollback_stmts: List[str] = []

    r2_bucket_env = os.getenv("R2_BUCKET") or os.getenv("R2_BUCKET_NAME")
    # Process rows
    for r in rows:
        table = r.get("table")
        row_id = r.get("id")
        column = r.get("column")
        before = r.get("before") or ""
        after = r.get("after") or ""

        # By default consider r2 path in 'after'
        bucket, key = parse_r2_path(after)
        r2_exists = False
        notes = ""

        if bucket and key:
            # If bucket missing in path, use default R2_BUCKET env
            if not bucket and r2_bucket_env:
                bucket = r2_bucket_env
            try:
                r2_exists = r2.blob_exists(bucket, key)
            except Exception as e:
                notes = f"check-error: {e}"
                r2_exists = False
        else:
            notes = "no-r2-after-path"

        verify_rows.append({
            "table": table,
            "id": row_id,
            "column": column,
            "after": after,
            "r2_exists": "yes" if r2_exists else "no",
            "notes": notes,
        })

        # Rollback: set column back to before (NULL if empty)
        if before == "":
            set_expr = f"{column} = NULL"
        else:
            set_expr = f"{column} = {quote_sql(before)}"

        stmt = f"UPDATE {table} SET {set_expr} WHERE id = {quote_sql(row_id)};"
        rollback_stmts.append(stmt)

    # Write verification CSV
    with VERIFY_CSV.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = ["table", "id", "column", "after", "r2_exists", "notes"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for vr in verify_rows:
            writer.writerow(vr)

    # Write rollback SQL
    with ROLLBACK_SQL.open("w", encoding="utf-8") as fh:
        fh.write("-- Rollback SQL generated from migration_audit_transcripts_and_covers.csv\n")
        fh.write("BEGIN;\n\n")
        for s in rollback_stmts:
            fh.write(s + "\n")
        fh.write("\nCOMMIT;\n")

    # Summary
    total = len(verify_rows)
    exists_count = sum(1 for v in verify_rows if v["r2_exists"] == "yes")
    missing_count = total - exists_count

    print(f"Verification written to: {VERIFY_CSV}")
    print(f"Rollback SQL written to: {ROLLBACK_SQL}")
    print(f"Total entries: {total}, exists in R2: {exists_count}, missing: {missing_count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
