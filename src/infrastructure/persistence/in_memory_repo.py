"""InMemoryPostRepository — Test double for unit tests. No external dependencies."""
from __future__ import annotations

from datetime import date

from src.domain.entities.post import Post
from src.domain.ports.post_repository import PostRepository
from src.domain.value_objects.post_status import PostStatus


class InMemoryPostRepository(PostRepository):
    """단위 테스트용 인메모리 저장소. 외부 의존 없음."""

    def __init__(self, posts: list[Post] | None = None):
        self._posts: list[Post] = posts or []
        self._cwv_records: dict[int, dict] = {}

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

    def find_failed(self) -> list[Post]:
        return [p for p in self._posts
                if p.status == PostStatus.FAILED]

    def find_published(self, limit: int = 50) -> list[Post]:
        return [p for p in self._posts
                if p.status == PostStatus.PUBLISHED][:limit]

    def find_revision_pending(self, limit: int = 5) -> list[Post]:
        return [p for p in self._posts
                if p.status == PostStatus.REVISION_PENDING][:limit]

    def find_revising_stuck(self) -> list[Post]:
        return [p for p in self._posts
                if p.status == PostStatus.REVISING]

    def find_cwv_unchecked(self, limit: int = 10) -> list[Post]:
        return [p for p in self._posts
                if p.status == PostStatus.PUBLISHED
                and p.row_index not in self._cwv_records][:limit]

    def save_cwv_record(
        self, row_index: int,
        lcp: float, cls_score: float,
    ) -> None:
        self._cwv_records[row_index] = {"lcp": lcp, "cls": cls_score}

    def find_all(self) -> list[Post]:
        return list(self._posts)

    def save_category(self, row_index: int, category: str) -> None:
        for post in self._posts:
            if post.row_index == row_index:
                post.category = category
                return

    def count_published_today(self) -> int:
        today = date.today()
        return sum(
            1 for p in self._posts
            if p.status == PostStatus.PUBLISHED
            and p.published_at is not None
            and p.published_at.date() == today
        )

    def add_keyword_row(self, keyword: str) -> int:
        row_index = len(self._posts) + 2  # 시트 헤더(1행) + 기존 데이터 다음
        post = Post(row_index=row_index, keyword=keyword)
        self._posts.append(post)
        return row_index

    def all(self) -> list[Post]:
        """테스트 검증용: 전체 포스트 반환."""
        return list(self._posts)
