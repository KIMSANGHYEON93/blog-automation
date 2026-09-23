"""용어 → 키워드 역방향 생성.

GSC는 '이미 노출된 쿼리'만 주므로 트래픽 없는 주제가 영원히 빠진다. 볼트 용어
381건은 트래픽과 무관한 시드라 이 루프를 끊는다(실측: 651개 키워드 산출).

기존 GSC 발굴과 같은 중복·B2C 필터를 재사용해 품질 기준을 맞춘다.
"""
from __future__ import annotations

import pytest

from src.application.use_cases.generate_keywords_from_terms import (
    GenerateKeywordsFromTermsUseCase,
)
from src.domain.ports.brain_term_port import BrainTermPort
from src.domain.value_objects.brain_term import BrainTerm
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


class FakeTerms(BrainTermPort):
    def __init__(self, terms: list[BrainTerm], fail: bool = False):
        self._terms = terms
        self._fail = fail

    def fetch_terms(self) -> list[BrainTerm]:
        if self._fail:
            raise RuntimeError("시트 조회 실패")
        return self._terms


def term(name: str, confusion: str = "") -> BrainTerm:
    return BrainTerm(name=name, definition=f"{name}의 정의", confusion_raw=confusion)


def make_use_case(terms, repo=None, **kw):
    return GenerateKeywordsFromTermsUseCase(
        repo=repo or InMemoryPostRepository(),
        term_port=FakeTerms(terms),
        **kw,
    )


class TestBasicGeneration:
    def test_정의형_키워드를_만든다(self):
        result = make_use_case([term("MCP")]).execute()
        assert result.success
        assert [s.keyword for s in result.suggestions] == ["MCP란"]

    def test_혼동포인트가_있으면_비교형도_만든다(self):
        uc = make_use_case([term("MCP", "MCP ≠ 에이전트. 설명")])
        kws = [s.keyword for s in uc.execute().suggestions]
        assert kws == ["MCP란", "MCP vs 에이전트 차이"]

    def test_용어가_없으면_빈_결과(self):
        result = make_use_case([]).execute()
        assert result.success
        assert result.suggestions == []

    def test_top_n으로_개수를_제한한다(self):
        uc = make_use_case([term(f"용어{i}") for i in range(10)], top_n=3)
        assert len(uc.execute().suggestions) == 3


class TestFiltering:
    def test_이미_쓴_키워드는_제외(self):
        repo = InMemoryPostRepository()
        repo.add_keyword_row("MCP란")
        uc = make_use_case([term("MCP"), term("RAG")], repo=repo)
        assert [s.keyword for s in uc.execute().suggestions] == ["RAG란"]

    def test_유사_키워드도_제외(self):
        """GSC 발굴과 같은 토큰 겹침 기준을 쓴다 — n8n이 어차피 중복 스킵한다."""
        repo = InMemoryPostRepository()
        repo.add_keyword_row("RAG vs 파인튜닝 차이")
        uc = make_use_case([term("RAG", "RAG ≠ 파인튜닝. 설명")], repo=repo)
        kws = [s.keyword for s in uc.execute().suggestions]
        assert "RAG vs 파인튜닝 차이" not in kws

    def test_B2C_노이즈는_제외(self):
        uc = make_use_case([term("기프트카드"), term("MCP")])
        kws = [s.keyword for s in uc.execute().suggestions]
        assert "MCP란" in kws
        assert not any("기프트카드" in k for k in kws)

    def test_같은_키워드가_두_번_나오지_않는다(self):
        uc = make_use_case([term("MCP"), term("MCP")])
        kws = [s.keyword for s in uc.execute().suggestions]
        assert len(kws) == len(set(kws))


class TestAutoRegister:
    def test_시트에_대기_상태로_등록한다(self):
        repo = InMemoryPostRepository()
        uc = make_use_case([term("MCP")], repo=repo)
        result = uc.execute(auto_register=True)
        assert result.registered == 1
        assert any(p.keyword == "MCP란" for p in repo.all())

    def test_등록하지_않으면_시트가_그대로다(self):
        repo = InMemoryPostRepository()
        make_use_case([term("MCP")], repo=repo).execute()
        assert repo.all() == []

    def test_등록_실패해도_전체가_죽지_않는다(self):
        class Flaky(InMemoryPostRepository):
            def add_keyword_row(self, keyword: str) -> int:
                if keyword == "MCP란":
                    raise RuntimeError("시트 쓰기 실패")
                return super().add_keyword_row(keyword)

        uc = make_use_case([term("MCP"), term("RAG")], repo=Flaky())
        result = uc.execute(auto_register=True)
        assert result.registered == 1


class TestFailureHandling:
    def test_용어_조회_실패는_success_False(self):
        uc = GenerateKeywordsFromTermsUseCase(
            repo=InMemoryPostRepository(),
            term_port=FakeTerms([], fail=True),
        )
        result = uc.execute()
        assert result.success is False
        assert result.error
        assert result.suggestions == []


class TestPortContract:
    def test_포트는_추상이다(self):
        with pytest.raises(TypeError):
            BrainTermPort()  # type: ignore[abstract]


class TestPriorityOrder:
    """볼트는 가나다순이라 마이너 용어가 앞에 온다 — 우선순위로 다시 세운다."""

    def test_우선순위_높은_용어가_먼저(self):
        minor = BrainTerm(name="계층형 에이전트 라우팅", definition="d")
        major = BrainTerm(name="MCP", definition="d",
                          aliases_raw="Model Context Protocol, MCP 서버",
                          source="spec.md")
        uc = make_use_case([minor, major])
        kws = [s.keyword for s in uc.execute().suggestions]
        assert kws[0] == "MCP란"

    def test_같은_용어_안에서는_정의형이_비교형보다_먼저(self):
        uc = make_use_case([BrainTerm(name="MCP", definition="d",
                                      confusion_raw="MCP ≠ 에이전트.")])
        kws = [s.keyword for s in uc.execute().suggestions]
        assert kws == ["MCP란", "MCP vs 에이전트 차이"]

    def test_top_n이_우선순위_상위를_자른다(self):
        minor = BrainTerm(name="계층형 에이전트 라우팅", definition="d")
        major = BrainTerm(name="RAG", definition="d", source="s")
        uc = make_use_case([minor, major], top_n=1)
        assert [s.keyword for s in uc.execute().suggestions] == ["RAG란"]
