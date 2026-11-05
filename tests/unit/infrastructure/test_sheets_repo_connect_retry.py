"""GoogleSheetsPostRepository 첫 연결 재시도.

00:00 키워드 발굴이 토큰 요청에서 SSL EOF로 가끔(25일 중 6일) 죽었다 — 같은 초에
재시도 3번이 다 실패. 잠깐 끊긴 연결만 간격을 두고 다시 시도한다.
"""
from __future__ import annotations

import pytest
import requests
from google.auth.exceptions import TransportError

from src.infrastructure.persistence import google_sheets_repo as repo_mod
from src.infrastructure.persistence.google_sheets_repo import GoogleSheetsPostRepository


class _FakeSpreadsheet:
    sheet1 = "first-tab"


class _FlakyClient:
    def __init__(self, errors: list[Exception]):
        self._errors = list(errors)
        self.calls = 0

    def open(self, name: str) -> _FakeSpreadsheet:
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        return _FakeSpreadsheet()


@pytest.fixture
def slept(monkeypatch) -> list[float]:
    waits: list[float] = []
    monkeypatch.setattr(repo_mod, "_sleep", waits.append)
    monkeypatch.setattr(
        repo_mod.GoogleCredentials, "from_service_account_file",
        lambda *args, **kwargs: object(),
    )
    return waits


def _use(monkeypatch, client: _FlakyClient) -> None:
    monkeypatch.setattr(repo_mod.gspread, "authorize", lambda *args, **kwargs: client)


def _repo() -> GoogleSheetsPostRepository:
    return GoogleSheetsPostRepository(creds_path="c.json", sheet_name="keyword_calendar_v2")


def test_잠깐_끊긴_연결은_기다렸다_다시_연다(monkeypatch, slept):
    client = _FlakyClient([TransportError("SSL EOF"), requests.exceptions.SSLError("EOF")])
    _use(monkeypatch, client)
    assert _repo()._sheet == "first-tab"
    assert client.calls == 3
    assert slept == [5, 15]


def test_계속_끊기면_마지막_오류를_올린다(monkeypatch, slept):
    client = _FlakyClient([TransportError("x")] * 4)
    _use(monkeypatch, client)
    with pytest.raises(TransportError):
        _repo()
    assert client.calls == 4
    assert slept == [5, 15, 45]


def test_연결_문제가_아닌_오류는_바로_올린다(monkeypatch, slept):
    client = _FlakyClient([ValueError("시트 없음")])
    _use(monkeypatch, client)
    with pytest.raises(ValueError):
        _repo()
    assert client.calls == 1
    assert slept == []
