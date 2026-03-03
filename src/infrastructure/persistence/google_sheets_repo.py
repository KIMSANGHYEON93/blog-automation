"""GoogleSheetsPostRepository — PostRepository implementation using gspread."""
from __future__ import annotations

import logging
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials as GoogleCredentials

from src.domain.entities.post import Post
from src.domain.ports.post_repository import PostRepository
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.column_map import (
    COL,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PUBLISHED,
    STATUS_PUBLISHING,
)

logger = logging.getLogger(__name__)

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


class GoogleSheetsPostRepository(PostRepository):
    def __init__(self, creds_path: str, sheet_name: str):
        creds = GoogleCredentials.from_service_account_file(creds_path, scopes=SCOPES)
        client = gspread.authorize(creds)
        self._sheet = client.open(sheet_name).sheet1
        self._header_row = 1  # 1행은 헤더

    def _row_to_post(self, row_values: list, row_index: int) -> Post:
        def get(col_key: str) -> str:
            idx = COL[col_key] - 1
            return row_values[idx] if idx < len(row_values) else ""

        content = None
        body = get("content")
        if body:
            content = PostContent(
                title=get("title"),
                body_markdown=body,
                meta_description=get("meta_desc"),
                faq_schema=get("faq"),
                tags=get("tags"),
                thumbnail_url=get("thumbnail_url"),
                internal_link_keywords=get("internal_links"),
            )

        return Post(
            row_index=row_index,
            keyword=get("keyword"),
            category=get("category"),
            content=content,
            status=PostStatus(get("status")) if get("status") else PostStatus.PENDING,
            published_url=get("published_url"),
            error_message=get("error_msg"),
            entry_id=get("entry_id"),
        )

    def find_pending(self, limit: int = 5) -> list[Post]:
        all_rows = self._sheet.get_all_values()
        result = []
        for i, row in enumerate(all_rows[self._header_row:], start=self._header_row + 1):
            status_val = row[COL["status"] - 1] if len(row) >= COL["status"] else ""
            if status_val == STATUS_PENDING:
                result.append(self._row_to_post(row, i))
                if len(result) >= limit:
                    break
        return result

    def find_stuck(self) -> list[Post]:
        all_rows = self._sheet.get_all_values()
        result = []
        for i, row in enumerate(all_rows[self._header_row:], start=self._header_row + 1):
            status_val = row[COL["status"] - 1] if len(row) >= COL["status"] else ""
            if status_val == STATUS_PUBLISHING:
                result.append(self._row_to_post(row, i))
        return result

    def find_failed(self) -> list[Post]:
        all_rows = self._sheet.get_all_values()
        result = []
        for i, row in enumerate(all_rows[self._header_row:], start=self._header_row + 1):
            status_val = row[COL["status"] - 1] if len(row) >= COL["status"] else ""
            if status_val == STATUS_FAILED:
                result.append(self._row_to_post(row, i))
        return result

    def find_published(self, limit: int = 50) -> list[Post]:
        all_rows = self._sheet.get_all_values()
        result = []
        for i, row in enumerate(all_rows[self._header_row:], start=self._header_row + 1):
            status_val = row[COL["status"] - 1] if len(row) >= COL["status"] else ""
            if status_val == STATUS_PUBLISHED:
                result.append(self._row_to_post(row, i))
                if len(result) >= limit:
                    break
        return result

    def find_cwv_unchecked(self, limit: int = 10) -> list[Post]:
        all_rows = self._sheet.get_all_values()
        result = []
        cwv_col = COL["cwv_checked_at"] - 1
        for i, row in enumerate(all_rows[self._header_row:], start=self._header_row + 1):
            status_val = row[COL["status"] - 1] if len(row) >= COL["status"] else ""
            cwv_val = row[cwv_col] if len(row) > cwv_col else ""
            if status_val == STATUS_PUBLISHED and not cwv_val.strip():
                result.append(self._row_to_post(row, i))
                if len(result) >= limit:
                    break
        return result

    def save(self, post: Post) -> None:
        row = post.row_index
        updates = {
            COL["status"]: post.status.value,
            COL["error_msg"]: post.error_message,
            COL["published_url"]: post.published_url,
        }
        if post.published_at:
            updates[COL["published_at"]] = post.published_at.strftime("%Y-%m-%d %H:%M:%S")
        if post.entry_id:
            updates[COL["entry_id"]] = post.entry_id

        for col, value in updates.items():
            self._sheet.update_cell(row, col, value)
        logger.debug(f"시트 업데이트: row={row}, status={post.status.value}")

    def save_cwv_record(
        self, row_index: int,
        lcp: float, cls_score: float,
    ) -> None:
        self._sheet.update_cell(row_index, COL["cwv_lcp"], f"{lcp:.2f}")
        self._sheet.update_cell(row_index, COL["cwv_cls"], f"{cls_score:.3f}")
        self._sheet.update_cell(
            row_index, COL["cwv_checked_at"],
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        logger.debug(f"CWV 기록: row={row_index}, LCP={lcp:.2f}, CLS={cls_score:.3f}")
