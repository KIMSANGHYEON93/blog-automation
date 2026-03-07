"""DiscoverKeywordsUseCase — GSC 데이터 기반 키워드 자동 발굴."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.domain.ports.keyword_port import KeywordResearchPort
from src.domain.ports.post_repository import PostRepository
from src.domain.value_objects.keyword_suggestion import KeywordSuggestion

logger = logging.getLogger(__name__)


@dataclass
class KeywordDiscoveryResult:
    """키워드 발굴 결과 DTO."""

    success: bool
    suggestions: list[KeywordSuggestion]
    total_queries: int = 0
    filtered: int = 0
    error: str = ""


class DiscoverKeywordsUseCase:
    """GSC 검색 데이터에서 키워드를 발굴하여 제안.

    필터링 전략:
    - impressions >= min_impressions (기본 50)
    - position < max_position (기본 20)
    - ctr < max_ctr (기본 0.03 = 3%)
    - 기존 키워드 중복 제외
    - opportunity_score = impressions × (1 - ctr) 내림차순 Top N
    """

    def __init__(
        self,
        repo: PostRepository,
        keyword_research: KeywordResearchPort,
        min_impressions: int = 50,
        max_position: float = 20.0,
        max_ctr: float = 0.03,
        top_n: int = 10,
    ):
        self._repo = repo
        self._keyword_research = keyword_research
        self._min_impressions = min_impressions
        self._max_position = max_position
        self._max_ctr = max_ctr
        self._top_n = top_n

    def execute(self, site_url: str, days: int = 28) -> KeywordDiscoveryResult:
        try:
            queries = self._keyword_research.fetch_queries(site_url, days=days)
        except Exception as e:
            logger.error(f"GSC 검색 데이터 조회 실패: {e}")
            return KeywordDiscoveryResult(
                success=False, suggestions=[], error=str(e)[:200],
            )

        if not queries:
            return KeywordDiscoveryResult(success=True, suggestions=[])

        # 기존 키워드 수집 (중복 제외용)
        all_posts = self._repo.find_all()
        existing_keywords = {p.keyword.lower().strip() for p in all_posts if p.keyword}

        # 필터링
        filtered = []
        for q in queries:
            if q.impressions < self._min_impressions:
                continue
            if q.position >= self._max_position:
                continue
            if q.ctr >= self._max_ctr:
                continue
            if q.keyword.lower().strip() in existing_keywords:
                continue
            filtered.append(q)

        # opportunity_score 내림차순 정렬 → Top N
        filtered.sort(key=lambda x: x.opportunity_score, reverse=True)
        suggestions = filtered[: self._top_n]

        logger.info(
            f"키워드 발굴: 전체 {len(queries)}건 → "
            f"필터링 {len(filtered)}건 → 제안 {len(suggestions)}건"
        )

        return KeywordDiscoveryResult(
            success=True,
            suggestions=suggestions,
            total_queries=len(queries),
            filtered=len(filtered),
        )
