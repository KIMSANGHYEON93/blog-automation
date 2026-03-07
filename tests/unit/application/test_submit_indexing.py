"""SubmitIndexingUseCase 테스트."""
from __future__ import annotations

from src.application.use_cases.submit_indexing import SubmitIndexingUseCase
from src.domain.entities.post import Post
from src.domain.ports.seo_port import IndexingSubmitPort, IndexingSubmitResult
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


class _StubSubmit(IndexingSubmitPort):
    """테스트용 IndexingSubmitPort 스텁."""

    def __init__(self, success: bool = True, error: str = ""):
        self._success = success
        self._error = error
        self.submitted_urls: list[str] = []

    def submit(self, url: str) -> IndexingSubmitResult:
        self.submitted_urls.append(url)
        return IndexingSubmitResult(url=url, success=self._success, error=self._error)


def _published_post(
    row: int = 2, keyword: str = "테스트",
    url: str = "https://example.tistory.com/1",
) -> Post:
    post = Post(row_index=row, keyword=keyword)
    post.status = PostStatus.PUBLISHED
    post.published_url = url
    return post


class TestSubmitIndexingUseCase:
    def test_발행완료_포스트_색인_제출(self):
        """발행 완료 포스트의 URL을 색인 API에 제출."""
        submit = _StubSubmit(success=True)
        repo = InMemoryPostRepository([
            _published_post(row=2, url="https://example.tistory.com/1"),
            _published_post(row=3, url="https://example.tistory.com/2"),
        ])
        uc = SubmitIndexingUseCase(repo, indexing_submit=submit)

        stats = uc.execute()

        assert stats.submitted == 2
        assert stats.failed == 0
        assert len(submit.submitted_urls) == 2

    def test_URL_없는_포스트_건너뜀(self):
        """published_url이 빈 포스트는 건너뜀."""
        submit = _StubSubmit()
        post_no_url = Post(row_index=4, keyword="없음")
        post_no_url.status = PostStatus.PUBLISHED
        repo = InMemoryPostRepository([_published_post(), post_no_url])
        uc = SubmitIndexingUseCase(repo, indexing_submit=submit)

        stats = uc.execute()

        assert stats.submitted == 1
        assert stats.skipped == 1

    def test_포스트_없으면_빈_통계(self):
        """발행 포스트 없으면 모두 0."""
        submit = _StubSubmit()
        repo = InMemoryPostRepository([])
        uc = SubmitIndexingUseCase(repo, indexing_submit=submit)

        stats = uc.execute()

        assert stats.submitted == 0
        assert stats.failed == 0

    def test_API_실패시_failed_증가(self):
        """API 오류 시 failed 카운트 증가."""
        submit = _StubSubmit(success=False, error="403 Forbidden")
        repo = InMemoryPostRepository([_published_post()])
        uc = SubmitIndexingUseCase(repo, indexing_submit=submit)

        stats = uc.execute()

        assert stats.submitted == 0
        assert stats.failed == 1

    def test_quota_초과시_조기_중단(self):
        """quota 에러 시 나머지 건너뜀."""
        submit = _StubSubmit(success=False, error="quota exceeded 429")
        repo = InMemoryPostRepository([
            _published_post(row=2),
            _published_post(row=3),
        ])
        uc = SubmitIndexingUseCase(repo, indexing_submit=submit)

        stats = uc.execute()

        assert stats.failed == 1
        assert len(submit.submitted_urls) == 1

    def test_단일_포스트_제출(self):
        """submit_single — 성공."""
        submit = _StubSubmit(success=True)
        repo = InMemoryPostRepository()
        uc = SubmitIndexingUseCase(repo, indexing_submit=submit)

        result = uc.submit_single(_published_post())

        assert result is True
        assert len(submit.submitted_urls) == 1

    def test_단일_포스트_미발행_상태_실패(self):
        """submit_single — PENDING은 제출 불가."""
        submit = _StubSubmit()
        repo = InMemoryPostRepository()
        uc = SubmitIndexingUseCase(repo, indexing_submit=submit)

        result = uc.submit_single(Post(row_index=2, keyword="테스트"))

        assert result is False
        assert len(submit.submitted_urls) == 0
