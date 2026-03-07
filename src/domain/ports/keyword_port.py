"""KeywordResearchPort — Domain interface for keyword research."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.value_objects.keyword_suggestion import KeywordSuggestion


class KeywordResearchPort(ABC):
    @abstractmethod
    def fetch_queries(
        self, site_url: str, days: int = 28,
    ) -> list[KeywordSuggestion]:
        """GSC Search Analytics에서 검색 쿼리 데이터 조회.

        Args:
            site_url: Search Console 속성 URL
            days: 조회 기간 (일)

        Returns:
            KeywordSuggestion 리스트 (opportunity_score 내림차순)
        """
        ...
