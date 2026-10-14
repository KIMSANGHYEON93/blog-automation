"""Pollinations — 키 계정이 크레딧 없음(402)이면 무료 주소로 다시 받는다(2026-10-08~14 사진 0장)."""
from __future__ import annotations

import requests

from src.infrastructure.image import pollinations_adapter as pa


class _Resp:
    def __init__(self, status: int, body: bytes = b"", ctype: str = "image/jpeg"):
        self.status_code, self.content = status, body
        self.headers = {"content-type": ctype}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error", response=self)


def _fake_get(responses: dict[str, _Resp], calls: list[str]):
    def get(url, headers=None, timeout=None):
        calls.append(url)
        host = "gen" if url.startswith(pa._BASE_URL) else "free"
        return responses[host]
    return get


def test_결제_필요면_무료_주소로_다시_받는다(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(pa.requests, "get", _fake_get(
        {"gen": _Resp(402), "free": _Resp(200, b"x" * 2048)}, calls))
    data, url = pa.fetch_image("blue sky", api_key="k", seed=1)
    assert data == b"x" * 2048
    assert url.startswith(pa._FREE_URL) and "nologo=true" in url
    assert len(calls) == 2


def test_키가_없으면_바로_무료_주소(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(pa.requests, "get", _fake_get(
        {"gen": _Resp(401), "free": _Resp(200, b"y" * 2048)}, calls))
    data, _ = pa.fetch_image("blue sky", api_key="", seed=1)
    assert data and len(calls) == 1 and calls[0].startswith(pa._FREE_URL)


def test_서버_오류는_무료로_넘기지_않고_실패(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(pa.requests, "get", _fake_get(
        {"gen": _Resp(500), "free": _Resp(200, b"z" * 2048)}, calls))
    try:
        pa.fetch_image("blue sky", api_key="k", seed=1)
        raise AssertionError("실패해야 한다")
    except RuntimeError:
        pass
    assert len(calls) == 1
