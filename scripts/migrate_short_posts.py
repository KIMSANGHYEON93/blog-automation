"""Migrate short pending posts to '검수필요' status.

Finds all '발행대기' posts with body < 3000 chars and marks them '검수필요'.
Run once after deploying MIN_CONTENT_LENGTH gate.

Usage:
    python scripts/migrate_short_posts.py --dry-run
    python scripts/migrate_short_posts.py
"""
from __future__ import annotations

import argparse

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
MIN_CONTENT_LENGTH = 3000
COL_STATUS = 3       # C열
COL_CONTENT = 15     # O열
COL_ERROR_MSG = 13   # M열


def main():
    parser = argparse.ArgumentParser(description="Migrate short posts to 검수필요")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change")
    parser.add_argument("--creds", default="credentials.json", help="Google credentials path")
    parser.add_argument("--sheet", default="blog-automation", help="Sheet name")
    args = parser.parse_args()

    creds = Credentials.from_service_account_file(args.creds, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open(args.sheet).sheet1

    all_rows = sheet.get_all_values()
    targets = []

    for i, row in enumerate(all_rows[1:], start=2):  # skip header
        status = row[COL_STATUS - 1] if len(row) >= COL_STATUS else ""
        content = row[COL_CONTENT - 1] if len(row) >= COL_CONTENT else ""
        keyword = row[0] if len(row) >= 1 else ""

        if status == "발행대기" and len(content) < MIN_CONTENT_LENGTH:
            targets.append((i, keyword, len(content)))

    if not targets:
        print("No short posts found. Nothing to migrate.")
        return

    print(f"Found {len(targets)} short posts:")
    for row_idx, kw, length in targets:
        print(f"  Row {row_idx}: {kw} ({length} chars)")

    if args.dry_run:
        print("\n--dry-run mode. No changes made.")
        return

    confirm = input(f"\nUpdate {len(targets)} posts to '검수필요'? [y/N] ")
    if confirm.lower() != "y":
        print("Aborted.")
        return

    from gspread import Cell
    cells = []
    for row_idx, kw, length in targets:
        cells.append(Cell(row=row_idx, col=COL_STATUS, value="검수필요"))
        cells.append(Cell(row=row_idx, col=COL_ERROR_MSG,
                          value=f"본문 {MIN_CONTENT_LENGTH}자 미만 ({length}자) - 자동 전환"))

    sheet.update_cells(cells)
    print(f"Updated {len(targets)} posts to '검수필요'.")


if __name__ == "__main__":
    main()
