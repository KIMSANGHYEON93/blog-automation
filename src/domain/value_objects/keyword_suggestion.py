"""KeywordSuggestion — Value Object for keyword research results."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeywordSuggestion:
    """GSC 검색 데이터 기반 키워드 제안."""

    keyword: str
    impressions: int = 0
    clicks: int = 0
    ctr: float = 0.0
    position: float = 0.0
    opportunity_score: float = 0.0

    @staticmethod
    def calculate_opportunity(impressions: int, ctr: float) -> float:
        """기회 점수 = impressions × (1 - ctr). 높을수록 개선 여지 큼."""
        return impressions * (1 - ctr)
