"""NaverSearchAdKeywordAdapter — 검색광고 API 키워드 도구(서명·파싱)."""
from __future__ import annotations

import base64
import hashlib
import hmac

import pytest

from src.infrastructure.seo import naver_searchad
from src.infrastructure.seo.naver_searchad import NaverSearchAdKeywordAdapter


class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def sent(monkeypatch):
    calls: list[dict] = []

    def fake_get(url, params, headers, timeout):
        calls.append({"url": url, "params": params, "headers": headers})
        return _Resp({"keywordList": [
            {"relKeyword": "연말정산계산기", "monthlyPcQcCnt": 1500, "monthlyMobileQcCnt": 1710},
            {"relKeyword": "연말정산교육", "monthlyPcQcCnt": "< 10", "monthlyMobileQcCnt": 20},
        ]})

    monkeypatch.setattr(naver_searchad.requests, "get", fake_get)
    monkeypatch.setattr(naver_searchad.time, "time", lambda: 1700000000.123)
    return calls


def test_PC와_모바일_검색량을_더하고_10_미만은_0으로(sent):
    rows = NaverSearchAdKeywordAdapter("key", "secret", "123").related(["연말정산"])
    assert [(r.keyword, r.monthly_searches) for r in rows] == [
        ("연말정산계산기", 3210), ("연말정산교육", 20),
    ]


def test_요청_서명과_힌트_형식(sent):
    NaverSearchAdKeywordAdapter("key", "secret", "123").related(["챗GPT 엑셀", "연말정산"])
    call = sent[0]
    # 힌트는 공백을 빼고 쉼표로 잇는다(공백이 있으면 API가 거부)
    assert call["params"] == {"hintKeywords": "챗GPT엑셀,연말정산", "showDetail": "1"}
    headers = call["headers"]
    assert headers["X-Timestamp"] == "1700000000123"
    assert (headers["X-API-KEY"], headers["X-Customer"]) == ("key", "123")
    expected = base64.b64encode(hmac.new(
        b"secret", b"1700000000123.GET./keywordstool", hashlib.sha256,
    ).digest()).decode()
    assert headers["X-Signature"] == expected


def test_HTTP_오류는_예외(monkeypatch):
    monkeypatch.setattr(naver_searchad.requests, "get",
                        lambda url, params, headers, timeout: _Resp({}, status=403))
    with pytest.raises(RuntimeError):
        NaverSearchAdKeywordAdapter("key", "secret", "123").related(["x"])
