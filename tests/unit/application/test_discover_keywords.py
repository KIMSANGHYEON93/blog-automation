"""DiscoverKeywordsUseCase 테스트."""
from __future__ import annotations

from src.application.use_cases.discover_keywords import DiscoverKeywordsUseCase
from src.domain.entities.post import Post
from src.domain.ports.keyword_port import KeywordResearchPort
from src.domain.value_objects.keyword_suggestion import KeywordSuggestion
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


class _StubKeywordResearch(KeywordResearchPort):
    def __init__(self, queries: list[KeywordSuggestion]):
        self._queries = queries

    def fetch_queries(self, site_url: str, days: int = 28) -> list[KeywordSuggestion]:
        return self._queries


class _ErrorKeywordResearch(KeywordResearchPort):
    def fetch_queries(self, site_url: str, days: int = 28) -> list[KeywordSuggestion]:
        raise RuntimeError("API 호출 실패")


def _suggestion(
    keyword: str, impressions: int = 100,
    ctr: float = 0.02, position: float = 10.0,
) -> KeywordSuggestion:
    return KeywordSuggestion(
        keyword=keyword,
        impressions=impressions,
        ctr=ctr,
        position=position,
        opportunity_score=KeywordSuggestion.calculate_opportunity(impressions, ctr),
    )


class TestDiscoverKeywordsUseCase:
    def test_필터링_후_제안(self):
        """조건에 맞는 키워드만 제안."""
        queries = [
            _suggestion("좋은 키워드", impressions=200, ctr=0.01, position=5.0),
            _suggestion("낮은 노출", impressions=2, ctr=0.01, position=5.0),
            _suggestion("높은 CTR", impressions=200, ctr=0.15, position=5.0),
            _suggestion("높은 순위", impressions=200, ctr=0.01, position=35.0),
        ]
        kr = _StubKeywordResearch(queries)
        repo = InMemoryPostRepository([])
        uc = DiscoverKeywordsUseCase(repo, kr)

        result = uc.execute("https://example.tistory.com/")

        assert result.success is True
        assert len(result.suggestions) == 1
        assert result.suggestions[0].keyword == "좋은 키워드"

    def test_기존_키워드_중복_제외(self):
        """이미 시트에 있는 키워드는 제외."""
        queries = [
            _suggestion("기존 키워드", impressions=200, ctr=0.01, position=5.0),
            _suggestion("신규 키워드", impressions=200, ctr=0.01, position=5.0),
        ]
        kr = _StubKeywordResearch(queries)
        repo = InMemoryPostRepository([
            Post(row_index=1, keyword="기존 키워드"),
        ])
        uc = DiscoverKeywordsUseCase(repo, kr)

        result = uc.execute("https://example.tistory.com/")

        assert len(result.suggestions) == 1
        assert result.suggestions[0].keyword == "신규 키워드"

    def test_Top_N_제한(self):
        """top_n 이상이면 잘림."""
        queries = [
            _suggestion(f"kw-{i}", impressions=200 - i, ctr=0.01, position=5.0)
            for i in range(20)
        ]
        kr = _StubKeywordResearch(queries)
        repo = InMemoryPostRepository([])
        uc = DiscoverKeywordsUseCase(repo, kr, top_n=5)

        result = uc.execute("https://example.tistory.com/")

        assert len(result.suggestions) == 5

    def test_빈_결과(self):
        """쿼리 없으면 빈 제안."""
        kr = _StubKeywordResearch([])
        repo = InMemoryPostRepository([])
        uc = DiscoverKeywordsUseCase(repo, kr)

        result = uc.execute("https://example.tistory.com/")

        assert result.success is True
        assert len(result.suggestions) == 0

    def test_API_실패(self):
        """API 오류 시 error 반환."""
        kr = _ErrorKeywordResearch()
        repo = InMemoryPostRepository([])
        uc = DiscoverKeywordsUseCase(repo, kr)

        result = uc.execute("https://example.tistory.com/")

        assert result.success is False
        assert "API 호출 실패" in result.error
