"""NaverSearchAdKeywordAdapter — 네이버 검색광고 API 키워드 도구(연관 키워드 + 월간 검색량).

공식 API(https://naver.github.io/searchad-apidoc/). 서명은 HMAC-SHA256("{ts}.GET.{uri}")을
base64로. 검색량은 최근 30일 PC·모바일 조회수이고, 10 미만은 "< 10" 문자열로 온다.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

import requests  # type: ignore[import-untyped]

from src.domain.ports.keyword_volume_port import KeywordVolumePort
from src.domain.value_objects.keyword_volume import KeywordVolume

API_BASE = "https://api.searchad.naver.com"
KEYWORD_TOOL = "/keywordstool"
TIMEOUT = 15


class NaverSearchAdKeywordAdapter(KeywordVolumePort):
    def __init__(self, api_key: str, secret: str, customer_id: str):
        self._api_key = api_key
        self._secret = secret
        self._customer_id = customer_id

    def related(self, hints: list[str]) -> list[KeywordVolume]:
        # 힌트에 공백이 있으면 API가 거부한다
        params = {"hintKeywords": ",".join("".join(h.split()) for h in hints),
                  "showDetail": "1"}
        resp = requests.get(API_BASE + KEYWORD_TOOL, params=params,
                            headers=self._headers("GET", KEYWORD_TOOL), timeout=TIMEOUT)
        resp.raise_for_status()
        return [
            KeywordVolume(row["relKeyword"],
                          _count(row.get("monthlyPcQcCnt")) + _count(row.get("monthlyMobileQcCnt")))
            for row in resp.json().get("keywordList", [])
        ]

    def _headers(self, method: str, uri: str) -> dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        digest = hmac.new(self._secret.encode(), f"{timestamp}.{method}.{uri}".encode(),
                          hashlib.sha256).digest()
        return {
            "X-Timestamp": timestamp,
            "X-API-KEY": self._api_key,
            "X-Customer": self._customer_id,
            "X-Signature": base64.b64encode(digest).decode(),
        }


def _count(value: object) -> int:
    """정수 또는 '< 10' — 10 미만은 추천 하한(수백)보다 한참 작으니 0으로 본다."""
    return value if isinstance(value, int) else 0
