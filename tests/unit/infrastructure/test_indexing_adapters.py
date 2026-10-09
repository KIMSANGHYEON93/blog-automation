"""색인 점검 어댑터 — URL Inspection 응답 파싱, 시트 수정 이력 읽기. 네트워크는 모두 모의."""
from __future__ import annotations

from datetime import datetime

from src.infrastructure.persistence import google_sheets_repo as repo_mod
from src.infrastructure.persistence.column_map import COL
from src.infrastructure.seo import indexing_checker


class _Call:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class _FakeService:
    def __init__(self, response):
        self._response = response

    def urlInspection(self):  # noqa: N802 — Google 클라이언트 이름 그대로
        return self

    def index(self):
        return self

    def inspect(self, body):
        return _Call(self._response)


def test_URL_Inspection_응답에서_진단_필드를_읽는다(monkeypatch):
    response = {"inspectionResult": {"indexStatusResult": {
        "verdict": "NEUTRAL", "coverageState": "Crawled - currently not indexed",
        "indexingState": "INDEXING_ALLOWED", "robotsTxtState": "ALLOWED",
        "pageFetchState": "SUCCESSFUL",
        "googleCanonical": "https://b.tistory.com/1", "userCanonical": "https://b.tistory.com/1",
    }}}
    monkeypatch.setenv("GOOGLE_CREDS", "c.json")
    monkeypatch.setattr(indexing_checker.GoogleCredentials, "from_service_account_file",
                        lambda *a, **k: object())
    monkeypatch.setattr(indexing_checker, "build", lambda *a, **k: _FakeService(response))

    result = indexing_checker.GscIndexingAdapter().check(
        "https://b.tistory.com/1", site_url="https://b.tistory.com/")

    assert not result.is_indexed
    assert result.page_fetch_state == "SUCCESSFUL"
    assert result.google_canonical == "https://b.tistory.com/1"
    assert result.user_canonical == "https://b.tistory.com/1"


def test_시트의_수정횟수와_최종수정일시를_읽는다():
    repo = repo_mod.GoogleSheetsPostRepository.__new__(repo_mod.GoogleSheetsPostRepository)
    row = [""] * max(COL.values())
    row[COL["keyword"] - 1] = "키워드"
    row[COL["status"] - 1] = "발행완료"
    row[COL["revision_count"] - 1] = "2"
    row[COL["revised_at"] - 1] = "2026-10-01 10:00:00"

    post = repo._row_to_post(row, 5)

    assert post.revision_count == 2
    assert post.revised_at == datetime(2026, 10, 1, 10, 0)

    row[COL["revision_count"] - 1] = "x"
    row[COL["revised_at"] - 1] = ""
    post = repo._row_to_post(row, 5)
    assert post.revision_count == 0
    assert post.revised_at is None
