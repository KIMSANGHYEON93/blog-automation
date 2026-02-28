"""Integration tests for GoogleSheetsPostRepository — uses REAL Google Sheets API.

Run with: pytest tests/integration/test_google_sheets_repo.py -m integration
Requires: credentials.json in project root and SHEET_NAME in .env
"""
from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.column_map import (
    COL,
    STATUS_PENDING,
    STATUS_PUBLISHING,
)
from src.infrastructure.persistence.google_sheets_repo import GoogleSheetsPostRepository

load_dotenv()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CREDS_PATH = os.getenv("GOOGLE_CREDS", "credentials.json")
SHEET_NAME = os.getenv("SHEET_NAME", "keyword_calendar_v2")

# Test data written to row 2 for verification
TEST_ROW = 2


def _has_credentials() -> bool:
    return os.path.exists(CREDS_PATH)


skip_no_creds = pytest.mark.skipif(
    not _has_credentials(),
    reason=f"credentials.json not found at {CREDS_PATH}",
)


@pytest.fixture(scope="module")
def repo():
    """Create a real GoogleSheetsPostRepository connected to the live sheet.

    Skips the entire module if credentials.json does not exist.
    """
    if not _has_credentials():
        pytest.skip(f"credentials.json not found at {CREDS_PATH}")

    return GoogleSheetsPostRepository(creds_path=CREDS_PATH, sheet_name=SHEET_NAME)


@pytest.fixture(scope="module")
def sheet(repo):
    """Expose the raw gspread worksheet for setup/teardown helpers."""
    return repo._sheet


@pytest.fixture(autouse=True)
def _backup_and_restore_row2(sheet):
    """Save row 2 state before each test and restore it afterward.

    This ensures tests do not leave dirty data in the shared sheet.
    """
    original_values = sheet.row_values(TEST_ROW)
    yield
    # Restore: pad with empty strings so the update covers all columns
    max_col = max(COL.values())
    while len(original_values) < max_col:
        original_values.append("")
    cell_range = sheet.range(TEST_ROW, 1, TEST_ROW, max_col)
    for cell, val in zip(cell_range, original_values):  # noqa: B905
        cell.value = val
    sheet.update_cells(cell_range)


def _write_test_row(sheet, *, status: str, keyword: str = "integ_test_kw",
                    category: str = "test_cat", title: str = "Test Title",
                    meta_desc: str = "Test meta", content: str = "# Test Body"):
    """Write a well-known test row at TEST_ROW with the given status."""
    max_col = max(COL.values())
    row_data = [""] * max_col
    row_data[COL["keyword"] - 1] = keyword
    row_data[COL["category"] - 1] = category
    row_data[COL["status"] - 1] = status
    row_data[COL["title"] - 1] = title
    row_data[COL["meta_desc"] - 1] = meta_desc
    row_data[COL["content"] - 1] = content

    cell_range = sheet.range(TEST_ROW, 1, TEST_ROW, max_col)
    for cell, val in zip(cell_range, row_data):  # noqa: B905
        cell.value = val
    sheet.update_cells(cell_range)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@skip_no_creds
class TestGoogleSheetsRepoIntegration:
    """Integration tests that hit the real Google Sheets API."""

    def test_connect_to_sheet(self, repo, sheet):
        """Verify that the repository can connect and read the sheet header."""
        header = sheet.row_values(1)
        assert len(header) > 0, "Sheet header row should not be empty"
        # The sheet object is alive and responsive
        assert sheet.title is not None

    def test_find_pending_returns_posts(self, repo, sheet):
        """Set a row to STATUS_PENDING, verify find_pending() picks it up."""
        _write_test_row(sheet, status=STATUS_PENDING)

        posts = repo.find_pending(limit=10)
        matching = [p for p in posts if p.keyword == "integ_test_kw"]
        assert len(matching) >= 1, "Expected at least one pending test post"

        post = matching[0]
        assert post.status == PostStatus.PENDING
        assert post.keyword == "integ_test_kw"

    def test_find_pending_empty_when_none(self, repo, sheet):
        """When no rows have STATUS_PENDING, find_pending() returns empty list."""
        # Overwrite row 2 with a non-pending status
        _write_test_row(sheet, status="발행완료", keyword="integ_test_kw_done")

        posts = repo.find_pending(limit=10)
        matching = [p for p in posts if p.keyword == "integ_test_kw_done"]
        assert len(matching) == 0, "No posts with done status should appear in pending"

    def test_save_updates_status(self, repo, sheet):
        """Create a pending post, save it with PUBLISHED status, verify the sheet cell."""
        _write_test_row(sheet, status=STATUS_PENDING)

        posts = repo.find_pending(limit=10)
        matching = [p for p in posts if p.keyword == "integ_test_kw"]
        assert len(matching) >= 1

        post = matching[0]
        post.mark_publishing()
        post.mark_published(url="https://example.com/test-post")
        repo.save(post)

        # Re-read the status cell directly from the sheet
        updated_status = sheet.cell(post.row_index, COL["status"]).value
        assert updated_status == "발행완료", f"Expected 발행완료, got {updated_status}"

        updated_url = sheet.cell(post.row_index, COL["published_url"]).value
        assert updated_url == "https://example.com/test-post"

    def test_find_stuck_returns_publishing(self, repo, sheet):
        """Set a row to STATUS_PUBLISHING, verify find_stuck() returns it."""
        _write_test_row(sheet, status=STATUS_PUBLISHING, keyword="integ_stuck_kw")

        stuck = repo.find_stuck()
        matching = [p for p in stuck if p.keyword == "integ_stuck_kw"]
        assert len(matching) >= 1, "Expected at least one stuck (publishing) post"

        post = matching[0]
        assert post.status == PostStatus.PUBLISHING

    def test_row_to_post_mapping(self, repo, sheet):
        """Verify that column mapping correctly populates the Post entity."""
        _write_test_row(
            sheet,
            status=STATUS_PENDING,
            keyword="mapping_kw",
            category="mapping_cat",
            title="Mapping Title",
            meta_desc="Mapping meta desc",
            content="# Mapping Body\n\nParagraph here.",
        )

        posts = repo.find_pending(limit=10)
        matching = [p for p in posts if p.keyword == "mapping_kw"]
        assert len(matching) >= 1

        post = matching[0]
        assert post.keyword == "mapping_kw"
        assert post.category == "mapping_cat"
        assert post.status == PostStatus.PENDING
        assert post.content is not None
        assert post.content.title == "Mapping Title"
        assert post.content.meta_description == "Mapping meta desc"
        assert post.content.body_markdown == "# Mapping Body\n\nParagraph here."
        assert post.content.has_body() is True
        assert post.row_index == TEST_ROW
