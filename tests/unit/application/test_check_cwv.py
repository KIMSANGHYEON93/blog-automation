"""CheckCwvUseCase 테스트 — 6건."""
from __future__ import annotations

from src.application.use_cases.check_cwv import CheckCwvUseCase
from src.domain.entities.post import Post
from src.domain.ports.seo_port import CwvPort, CwvResult
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


class _StubCwv(CwvPort):
    """테스트용 CwvPort 스텁."""

    def __init__(self, result: CwvResult):
        self._result = result

    def check(self, url: str) -> CwvResult:
        return self._result


def _published_post(row: int = 2, keyword: str = "테스트") -> Post:
    post = Post(row_index=row, keyword=keyword)
    post.status = PostStatus.PUBLISHED
    post.published_url = "https://example.tistory.com/1"
    return post


def _mock_cwv_result(lcp: float = 1.5, cls_val: float = 0.05, score: int = 90) -> CwvResult:
    return CwvResult(
        lcp_seconds=lcp,
        cls_score=cls_val,
        performance_score=score,
        passed=lcp < 2.5,
    )


class TestCheckCwvUseCase:
    def test_CWV_통과(self):
        """mock API 응답 (LCP 1.5s) → passed=True."""
        cwv = _StubCwv(_mock_cwv_result(lcp=1.5))
        repo = InMemoryPostRepository([_published_post()])
        uc = CheckCwvUseCase(repo, cwv=cwv)

        result = uc.execute(_published_post())

        assert result.success is True
        assert result.passed is True
        assert result.lcp == 1.5

    def test_CWV_미통과(self):
        """mock API 응답 (LCP 3.0s) → passed=False."""
        cwv = _StubCwv(_mock_cwv_result(lcp=3.0))
        repo = InMemoryPostRepository([_published_post()])
        uc = CheckCwvUseCase(repo, cwv=cwv)

        result = uc.execute(_published_post())

        assert result.success is True
        assert result.passed is False
        assert result.lcp == 3.0

    def test_미발행_포스트_실패(self):
        """PENDING post → error."""
        cwv = _StubCwv(_mock_cwv_result())
        repo = InMemoryPostRepository()
        uc = CheckCwvUseCase(repo, cwv=cwv)
        post = Post(row_index=2, keyword="테스트")  # status=PENDING (default)

        result = uc.execute(post)

        assert result.success is False
        assert "발행완료 상태가 아닙니다" in result.error

    def test_CWV_결과_시트_저장(self):
        """execute 후 cwv_records에 기록 확인."""
        cwv = _StubCwv(_mock_cwv_result(lcp=2.0, cls_val=0.1))
        repo = InMemoryPostRepository([_published_post(row=5)])
        uc = CheckCwvUseCase(repo, cwv=cwv)

        uc.execute(_published_post(row=5))

        assert 5 in repo._cwv_records
        assert repo._cwv_records[5]["lcp"] == 2.0
        assert repo._cwv_records[5]["cls"] == 0.1


class TestFindCwvUnchecked:
    def test_미점검_포스트만_반환(self):
        """CWV 기록 없는 PUBLISHED 포스트만 반환."""
        repo = InMemoryPostRepository([
            _published_post(row=2),
            _published_post(row=3),
        ])
        repo._cwv_records[2] = {"lcp": 1.5, "cls": 0.05}

        unchecked = repo.find_cwv_unchecked()

        assert len(unchecked) == 1
        assert unchecked[0].row_index == 3

    def test_PENDING_포스트_제외(self):
        """PENDING 상태 포스트는 CWV 대상 아님."""
        pending = Post(row_index=2, keyword="대기중")
        repo = InMemoryPostRepository([pending, _published_post(row=3)])

        unchecked = repo.find_cwv_unchecked()

        assert len(unchecked) == 1
        assert unchecked[0].row_index == 3
