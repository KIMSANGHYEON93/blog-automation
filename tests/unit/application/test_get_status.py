"""GetStatusUseCase 테스트."""
from __future__ import annotations

from src.application.use_cases.get_status import GetStatusUseCase
from src.domain.entities.post import Post
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


def _post(row: int, status: PostStatus, url: str = "") -> Post:
    post = Post(row_index=row, keyword=f"kw-{row}")
    post.status = status
    post.published_url = url
    return post


class TestGetStatusUseCase:
    def test_상태별_카운트(self):
        """각 상태별 포스트 수 집계."""
        repo = InMemoryPostRepository([
            _post(1, PostStatus.PENDING),
            _post(2, PostStatus.PENDING),
            _post(3, PostStatus.PUBLISHED, "https://example.com/1"),
            _post(4, PostStatus.PUBLISHED, "https://example.com/2"),
            _post(5, PostStatus.PUBLISHED, "https://example.com/3"),
            _post(6, PostStatus.FAILED),
            _post(7, PostStatus.REVISION_PENDING),
        ])
        uc = GetStatusUseCase(repo)

        report = uc.execute()

        assert report.total == 7
        assert report.pending == 2
        assert report.published == 3
        assert report.failed == 1
        assert report.revision_pending == 1

    def test_빈_저장소(self):
        """포스트 없으면 모두 0."""
        repo = InMemoryPostRepository([])
        uc = GetStatusUseCase(repo)

        report = uc.execute()

        assert report.total == 0
        assert report.pending == 0
        assert report.published == 0

    def test_포맷_리포트(self):
        """format_report 출력 포맷."""
        repo = InMemoryPostRepository([
            _post(1, PostStatus.PUBLISHED, "https://example.com/1"),
        ])
        uc = GetStatusUseCase(repo)
        report = uc.execute()

        output = uc.format_report(report)

        assert "Blog Automation Status" in output
        assert "발행완료: 1" in output
