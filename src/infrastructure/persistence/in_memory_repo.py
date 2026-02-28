"""InMemoryPostRepository — Test double for unit tests. No external dependencies."""
from __future__ import annotations

from src.domain.entities.post import Post
from src.domain.ports.post_repository import PostRepository
from src.domain.value_objects.post_status import PostStatus


class InMemoryPostRepository(PostRepository):
    """단위 테스트용 인메모리 저장소. 외부 의존 없음."""

    def __init__(self, posts: list[Post] | None = None):
        self._posts: list[Post] = posts or []

    def find_pending(self, limit: int = 5) -> list[Post]:
        return [p for p in self._posts
                if p.status == PostStatus.PENDING][:limit]

    def save(self, post: Post) -> None:
        for i, p in enumerate(self._posts):
            if p.row_index == post.row_index:
                self._posts[i] = post
                return
        self._posts.append(post)

    def find_stuck(self) -> list[Post]:
        return [p for p in self._posts
                if p.status == PostStatus.PUBLISHING]

    def all(self) -> list[Post]:
        """테스트 검증용: 전체 포스트 반환."""
        return list(self._posts)
