"""GoogleSheetsPostRepository 행 ↔ Post 매핑 — 재시도·수정 이력·검증 지문 열 (gspread 없이)."""
from __future__ import annotations

from datetime import datetime

from src.domain.entities.post import Post
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.column_map import COL
from src.infrastructure.persistence.google_sheets_repo import GoogleSheetsPostRepository


class FakeSheet:
    def __init__(self, col_count: int = max(COL.values())):
        self.col_count = col_count
        self.cells: dict[tuple[int, int], str] = {}

    def update_cells(self, cells) -> None:
        for c in cells:
            assert c.col <= self.col_count, f"격자 밖 열 {c.col}"
            self.cells[(c.row, c.col)] = c.value

    def row(self, row: int) -> list[str]:
        width = max(col for (_, col) in self.cells) if self.cells else 0
        return [self.cells.get((row, col), "") for col in range(1, width + 1)]


def _repo(sheet: FakeSheet) -> GoogleSheetsPostRepository:
    repo = GoogleSheetsPostRepository.__new__(GoogleSheetsPostRepository)
    repo._sheet = sheet
    repo._header_row = 1
    return repo


def _row(**values: str) -> list[str]:
    row = [""] * max(COL.values())
    row[COL["keyword"] - 1] = "OAuth 개념"
    for key, value in values.items():
        row[COL[key] - 1] = value
    return row


def test_재시도_정보는_저장_후_다시_읽어도_유지된다():
    sheet = FakeSheet()
    repo = _repo(sheet)
    retry_at = datetime(2026, 10, 9, 13, 0, 0)
    post = Post(row_index=5, keyword="OAuth 개념", status=PostStatus.FAILED,
                error_message="timeout", retry_count=2, next_retry_at=retry_at)

    repo.save(post)
    back = repo._row_to_post(sheet.row(5), 5)

    assert back.retry_count == 2
    assert back.next_retry_at == retry_at


def test_새_열이_없는_예전_시트_행은_기본값():
    old_row = _row(status="발행실패")[: COL["revision_reason"]]  # A~AH까지만
    post = _repo(FakeSheet())._row_to_post(old_row, 5)
    assert post.retry_count == 0 and post.next_retry_at is None
    assert post.verified_body_hash == "" and post.approved_body_hash == ""


def test_새_열을_아직_안_만든_시트에는_그_열을_쓰지_않는다():
    sheet = FakeSheet(col_count=COL["revision_reason"])  # 마이그레이션 전 격자
    post = Post(row_index=5, keyword="k", status=PostStatus.FAILED, retry_count=1)
    _repo(sheet).save(post)  # 격자 밖 쓰기면 FakeSheet가 실패시킨다
    assert sheet.cells[(5, COL["status"])] == "발행실패"


def test_수정_이력은_Post_값으로_기록하고_최초_발행일은_덮지_않는다():
    sheet = FakeSheet()
    first = datetime(2026, 9, 1, 9, 0, 0)
    revised = datetime(2026, 10, 9, 10, 0, 0)
    post = Post(row_index=5, keyword="k", status=PostStatus.PUBLISHED, published_at=first,
                entry_id="1", published_url="https://t/1", revision_count=3, revised_at=revised)

    _repo(sheet).save(post)
    back = _repo(sheet)._row_to_post(sheet.row(5), 5)

    assert back.published_at == first
    assert back.revised_at == revised
    assert back.revision_count == 3


def test_검증_지문과_승인_지문을_저장하고_읽는다():
    sheet = FakeSheet()
    post = Post(row_index=5, keyword="k", verified_body_hash="aa", approved_body_hash="bb")
    _repo(sheet).save(post)
    back = _repo(sheet)._row_to_post(sheet.row(5), 5)
    assert (back.verified_body_hash, back.approved_body_hash) == ("aa", "bb")
