"""DiscoverKeywordsUseCase 테스트."""
from __future__ import annotations

from src.application.use_cases.discover_keywords import DiscoverKeywordsUseCase
from src.domain.entities.post import Post
from src.domain.ports.keyword_port import KeywordResearchPort
from src.domain.value_objects.keyword_suggestion import KeywordSuggestion
from src.domain.value_objects.post_status import PostStatus
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


class TestB2CBlocklist:
    """실제 GSC 데이터에서 자동 등록된 B2C 잡음 키워드 (2026-09-21)."""

    JUNK = [
        "invalid address 인도",
        "인도 your purchase could not be completed 해결",
        "애플 인도 payment method required",
        "애플 인도 계정 만들기",
        "payment method required 인도",
        "codex 나무위키",
    ]
    KEEP = [
        "rabbitmq 502 bad gateway",
        "nginx 502",
        "aadsts50105",
        "aks eks",
        "ssl 인증서 오류",
        "인도네시아 데이터센터 리전 선택",  # '인도' 부분 문자열로 막히면 안 됨
    ]

    def _run(self, keywords: list[str]) -> set[str]:
        kr = _StubKeywordResearch([_suggestion(k) for k in keywords])
        uc = DiscoverKeywordsUseCase(InMemoryPostRepository([]), kr, top_n=50)
        return {s.keyword for s in uc.execute("https://example.tistory.com/").suggestions}

    def test_B2C_잡음_키워드_제외(self):
        assert self._run(self.JUNK) == set()

    def test_B2B_IT_키워드는_유지(self):
        assert self._run(self.KEEP) == set(self.KEEP)


class TestNearDuplicateFilter:
    """n8n Pipeline A가 토큰 겹침 70%로 건너뛸 키워드는 애초에 등록하지 않는다."""

    def _run(self, existing_keywords: list[str], candidates: list[str]) -> set[str]:
        posts = [
            Post(row_index=i, keyword=kw, status=PostStatus.PUBLISHED)
            for i, kw in enumerate(existing_keywords, start=2)
        ]
        kr = _StubKeywordResearch([_suggestion(k) for k in candidates])
        uc = DiscoverKeywordsUseCase(InMemoryPostRepository(posts), kr, top_n=50)
        return {s.keyword for s in uc.execute("https://example.tistory.com/").suggestions}

    def test_대소문자_어미만_다른_기존_키워드는_제외(self):
        result = self._run(
            ["SSH 접속 Permission denied 해결"],
            ["ssh permission denied", "Kafka 파티션 재분배 전략"],
        )
        assert result == {"Kafka 파티션 재분배 전략"}

    def test_토큰_겹침이_기준_미만이면_등록(self):
        result = self._run(
            ["n8n 자동화 워크플로우 실전 구축"],
            ["n8n api를 통한 확장성과 자동화"],
        )
        assert result == {"n8n api를 통한 확장성과 자동화"}
