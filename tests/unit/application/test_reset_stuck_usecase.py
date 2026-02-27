"""Unit tests for ResetStuckPostsUseCase — TDD RED phase."""
import pytest

from src.application.use_cases.reset_stuck_posts import ResetStuckPostsUseCase
from src.domain.entities.post import Post
from src.domain.value_objects.post_status import PostStatus
from src.domain.value_objects.post_content import PostContent
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


class TestResetStuckPosts:
    """고스트 포스트 복구 테스트."""

    def test_고스트_1건_복구(self):
        stuck = Post(
            row_index=1,
            keyword="AD란",
            status=PostStatus.PUBLISHING,
            content=PostContent(title="제목", body_markdown="내용"),
        )
        repo = InMemoryPostRepository([stuck])
        use_case = ResetStuckPostsUseCase(repo=repo)

        count = use_case.execute()

        assert count == 1
        recovered = repo.all()[0]
        assert recovered.status == PostStatus.PENDING
        assert "자동 복구" in recovered.error_message

    def test_고스트_여러건_복구(self):
        posts = [
            Post(row_index=1, keyword="AD란", status=PostStatus.PUBLISHING,
                 content=PostContent(title="제목1", body_markdown="내용1")),
            Post(row_index=2, keyword="SSO란", status=PostStatus.PUBLISHING,
                 content=PostContent(title="제목2", body_markdown="내용2")),
            Post(row_index=3, keyword="SAML이란", status=PostStatus.PENDING,
                 content=PostContent(title="제목3", body_markdown="내용3")),
        ]
        repo = InMemoryPostRepository(posts)
        use_case = ResetStuckPostsUseCase(repo=repo)

        count = use_case.execute()

        assert count == 2
        assert repo.all()[0].status == PostStatus.PENDING
        assert repo.all()[1].status == PostStatus.PENDING
        assert repo.all()[2].status == PostStatus.PENDING  # 원래 PENDING

    def test_빈_목록_처리(self):
        repo = InMemoryPostRepository([])
        use_case = ResetStuckPostsUseCase(repo=repo)

        count = use_case.execute()

        assert count == 0

    def test_stuck_없으면_0_반환(self):
        post = Post(
            row_index=1,
            keyword="AD란",
            status=PostStatus.PUBLISHED,
            content=PostContent(title="제목", body_markdown="내용"),
        )
        repo = InMemoryPostRepository([post])
        use_case = ResetStuckPostsUseCase(repo=repo)

        count = use_case.execute()

        assert count == 0
        assert repo.all()[0].status == PostStatus.PUBLISHED
