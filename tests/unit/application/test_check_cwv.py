"""CheckCwvUseCase 테스트 — 6건."""
from __future__ import annotations

from unittest.mock import patch

from src.application.use_cases.check_cwv import CheckCwvUseCase
from src.domain.entities.post import Post
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository
from src.infrastructure.seo.cwv_checker import CwvResult


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
    @patch("src.application.use_cases.check_cwv.check_cwv")
    def test_CWV_통과(self, mock_check):
        """mock API 응답 (LCP 1.5s) → passed=True."""
        mock_check.return_value = _mock_cwv_result(lcp=1.5)
        repo = InMemoryPostRepository([_published_post()])
        uc = CheckCwvUseCase(repo)

        result = uc.execute(_published_post())

        assert result.success is True
        assert result.passed is True
        assert result.lcp == 1.5

    @patch("src.application.use_cases.check_cwv.check_cwv")
    def test_CWV_미통과(self, mock_check):
        """mock API 응답 (LCP 3.0s) → passed=False."""
        mock_check.return_value = _mock_cwv_result(lcp=3.0)
        repo = InMemoryPostRepository([_published_post()])
        uc = CheckCwvUseCase(repo)

        result = uc.execute(_published_post())

        assert result.success is True
        assert result.passed is False
        assert result.lcp == 3.0

    def test_미발행_포스트_실패(self):
        """PENDING post → error."""
        repo = InMemoryPostRepository()
        uc = CheckCwvUseCase(repo)
        post = Post(row_index=2, keyword="테스트")  # status=PENDING (default)

        result = uc.execute(post)

        assert result.success is False
        assert "발행완료 상태가 아닙니다" in result.error

    @patch("src.application.use_cases.check_cwv.check_cwv")
    def test_CWV_결과_시트_저장(self, mock_check):
        """execute 후 cwv_records에 기록 확인."""
        mock_check.return_value = _mock_cwv_result(lcp=2.0, cls_val=0.1)
        repo = InMemoryPostRepository([_published_post(row=5)])
        uc = CheckCwvUseCase(repo)

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
