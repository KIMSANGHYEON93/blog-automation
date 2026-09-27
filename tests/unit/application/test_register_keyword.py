"""RegisterKeywordUseCase — 관리자가 직접 넣는 키워드, 두 탭 모두와 중복 검사."""
import pytest

from src.application.use_cases.register_keyword import (
    DuplicateKeywordError,
    RegisterKeywordUseCase,
)
from src.domain.entities.post import Post
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


def _setup():
    naver = InMemoryPostRepository([Post(row_index=2, keyword="MCP란")])
    tistory = InMemoryPostRepository([Post(row_index=2, keyword="Gemini API 사용법 가이드")])
    return naver, RegisterKeywordUseCase(naver, other_repos=[tistory])


def test_새_키워드는_등록한다():
    naver, uc = _setup()
    row = uc.register("  감마 AI PPT 만들기 ")
    assert any(p.row_index == row and p.keyword == "감마 AI PPT 만들기" for p in naver.all())


@pytest.mark.parametrize("keyword, match", [
    ("MCP란", "MCP란"),                          # 같은 탭
    ("Gemini API 사용법", "Gemini API 사용법 가이드"),  # 다른 탭(티스토리), 토큰 겹침
])
def test_중복이면_겹친_키워드를_알려주고_등록하지_않는다(keyword, match):
    naver, uc = _setup()
    with pytest.raises(DuplicateKeywordError) as err:
        uc.register(keyword)
    assert err.value.matched == match
    assert len(naver.all()) == 1
