"""CheckIndexingUseCase 테스트 — 6건."""
from __future__ import annotations

from src.application.use_cases.check_indexing import CheckIndexingUseCase
from src.domain.entities.post import Post
from src.domain.ports.seo_port import IndexingPort, IndexingResult
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


class _StubIndexing(IndexingPort):
    """테스트용 IndexingPort 스텁."""

    def __init__(self, result: IndexingResult):
        self._result = result

    def check(self, url: str) -> IndexingResult:
        return self._result


def _published_post(row: int = 2, keyword: str = "테스트") -> Post:
    post = Post(row_index=row, keyword=keyword)
    post.status = PostStatus.PUBLISHED
    post.published_url = "https://example.tistory.com/1"
    return post


class TestCheckIndexingUseCase:
    def test_색인됨_포스트_상태유지(self):
        """색인된 포스트는 PUBLISHED 상태 유지."""
        indexing = _StubIndexing(IndexingResult(
            url="https://example.tistory.com/1",
            is_indexed=True,
            verdict="PASS",
            coverage_state="Submitted and indexed",
        ))
        repo = InMemoryPostRepository([_published_post()])
        uc = CheckIndexingUseCase(repo, indexing=indexing)

        result = uc.execute(_published_post())

        assert result.success is True
        assert result.is_indexed is True
        assert result.marked_revision is False

    def test_미색인_포스트_수정대기_전환(self):
        """미색인 포스트는 REVISION_PENDING으로 전환."""
        indexing = _StubIndexing(IndexingResult(
            url="https://example.tistory.com/1",
            is_indexed=False,
            verdict="FAIL",
            coverage_state="Discovered - currently not indexed",
        ))
        post = _published_post(row=3)
        repo = InMemoryPostRepository([post])
        uc = CheckIndexingUseCase(repo, indexing=indexing)

        result = uc.execute(post)

        assert result.success is True
        assert result.is_indexed is False
        assert result.marked_revision is True
        saved = repo.all()
        assert saved[0].status == PostStatus.REVISION_PENDING
        assert "색인 미생성" in saved[0].error_message

    def test_미발행_포스트_실패(self):
        """PENDING 포스트는 점검 대상 아님."""
        indexing = _StubIndexing(IndexingResult(url=""))
        repo = InMemoryPostRepository()
        uc = CheckIndexingUseCase(repo, indexing=indexing)
        post = Post(row_index=2, keyword="테스트")

        result = uc.execute(post)

        assert result.success is False
        assert "발행완료 상태가 아닙니다" in result.error

    def test_URL_없는_포스트_실패(self):
        """발행 URL이 없는 포스트는 점검 불가."""
        indexing = _StubIndexing(IndexingResult(url=""))
        repo = InMemoryPostRepository()
        uc = CheckIndexingUseCase(repo, indexing=indexing)
        post = Post(row_index=2, keyword="테스트")
        post.status = PostStatus.PUBLISHED

        result = uc.execute(post)

        assert result.success is False
        assert "발행 URL이 없습니다" in result.error

    def test_API_오류시_실패(self):
        """GSC API 오류 시 error 반환."""
        indexing = _StubIndexing(IndexingResult(
            url="https://example.tistory.com/1",
            error="403 Forbidden",
        ))
        repo = InMemoryPostRepository([_published_post()])
        uc = CheckIndexingUseCase(repo, indexing=indexing)

        result = uc.execute(_published_post())

        assert result.success is False
        assert "403" in result.error

    def test_미색인_사유_error_message에_저장(self):
        """미색인 사유가 Post.error_message에 기록됨."""
        indexing = _StubIndexing(IndexingResult(
            url="https://example.tistory.com/1",
            is_indexed=False,
            verdict="NEUTRAL",
            coverage_state="Crawled - currently not indexed",
        ))
        post = _published_post(row=5)
        repo = InMemoryPostRepository([post])
        uc = CheckIndexingUseCase(repo, indexing=indexing)

        uc.execute(post)

        saved = repo.all()
        assert "Crawled - currently not indexed" in saved[0].error_message
