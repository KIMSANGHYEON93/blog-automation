"""KeywordVolume — 검색 키워드와 월간 검색량(PC+모바일)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeywordVolume:
    keyword: str
    monthly_searches: int
