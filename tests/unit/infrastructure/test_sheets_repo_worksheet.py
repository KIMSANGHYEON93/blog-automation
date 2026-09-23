"""GoogleSheetsPostRepository 탭 선택 — 네이버 글은 같은 파일의 naver_calendar 탭에 둔다."""
from __future__ import annotations

import pytest

from src.infrastructure.persistence import google_sheets_repo as repo_mod
from src.infrastructure.persistence.google_sheets_repo import GoogleSheetsPostRepository


class _FakeSpreadsheet:
    sheet1 = "first-tab"

    def worksheet(self, title: str) -> str:
        return f"tab:{title}"


class _FakeClient:
    def open(self, name: str) -> _FakeSpreadsheet:
        return _FakeSpreadsheet()


@pytest.fixture(autouse=True)
def _no_google(monkeypatch):
    monkeypatch.setattr(
        repo_mod.GoogleCredentials, "from_service_account_file",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(repo_mod.gspread, "authorize", lambda *args, **kwargs: _FakeClient())


def test_worksheet_미지정이면_첫_탭():
    repo = GoogleSheetsPostRepository(creds_path="c.json", sheet_name="keyword_calendar_v2")
    assert repo._sheet == "first-tab"


def test_worksheet_지정하면_그_탭():
    repo = GoogleSheetsPostRepository(
        creds_path="c.json", sheet_name="keyword_calendar_v2", worksheet="naver_calendar",
    )
    assert repo._sheet == "tab:naver_calendar"
