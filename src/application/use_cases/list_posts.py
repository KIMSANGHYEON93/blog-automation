"""ListPostsUseCase — 관리자 대시보드용 게시물 목록/상세 조회 (읽기 전용)."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from src.application.use_cases.edit_post import EDITABLE_STATUSES
from src.application.use_cases.publish_selected_post import publish_blockers
from src.domain.entities.post import Post
from src.domain.ports.post_repository import PostRepository
from src.domain.value_objects.post_status import PostStatus

RECENT_PUBLISHED = 5


@dataclass(frozen=True)
class PostQuery:
    status: PostStatus | None = None
    search: str = ""


@dataclass(frozen=True)
class PostSummary:
    row_index: int
    keyword: str
    status: PostStatus
    title: str
    category: str
    body_length: int
    quality_score: int
    published_url: str
    published_at: str
    error_message: str
    meta_description: str
    blockers: tuple[str, ...]
    body_markdown: str = ""
    tags: str = ""

    @property
    def can_publish(self) -> bool:
        return not self.blockers

    @property
    def can_edit(self) -> bool:
        return self.status in EDITABLE_STATUSES

    @property
    def can_restore(self) -> bool:
        return self.status in (PostStatus.FAILED, PostStatus.HOLD)

    @property
    def can_regenerate(self) -> bool:
        statuses = (PostStatus.PENDING, PostStatus.HOLD, PostStatus.FAILED)
        return self.status in statuses and not self.published_url

    @property
    def can_archive(self) -> bool:
        return self.status == PostStatus.PENDING


@dataclass(frozen=True)
class PostPage:
    items: tuple[PostSummary, ...]
    counts: dict[PostStatus, int] = field(default_factory=dict)
    total: int = 0
    published_today: int = 0
    recent_published: tuple[PostSummary, ...] = ()  # 필터와 무관하게 최신 발행 순


def summarize(post: Post) -> PostSummary:
    content = post.content
    return PostSummary(
        row_index=post.row_index,
        keyword=post.keyword,
        status=post.status,
        title=content.title_or_fallback(post.keyword) if content else post.keyword,
        category=post.category,
        body_length=len(content.body_markdown or "") if content else 0,
        quality_score=post.quality_score,
        published_url=post.published_url,
        published_at=post.published_at.strftime("%Y-%m-%d %H:%M") if post.published_at else "",
        error_message=post.error_message,
        meta_description=content.meta_description if content else "",
        blockers=tuple(publish_blockers(post)),
        body_markdown=(content.body_markdown or "") if content else "",
        tags=content.tags if content else "",
    )


def _matches(post: Post, query: PostQuery) -> bool:
    if query.status is not None and post.status != query.status:
        return False
    needle = query.search.strip().lower()
    if not needle:
        return True
    title = (post.content.title or "") if post.content else ""
    return needle in post.keyword.lower() or needle in title.lower()


class ListPostsUseCase:
    def __init__(self, repo: PostRepository):
        self._repo = repo

    def execute(self, query: PostQuery) -> PostPage:
        posts = self._repo.find_all()
        counts = Counter(p.status for p in posts)
        items = tuple(summarize(p) for p in posts if _matches(p, query))
        published = sorted(
            (p for p in posts if p.status == PostStatus.PUBLISHED and p.published_at),
            key=lambda p: p.published_at or datetime.min, reverse=True,
        )
        today = date.today()
        return PostPage(
            items=items, counts=dict(counts), total=len(posts),
            published_today=sum(
                1 for p in published if p.published_at and p.published_at.date() == today
            ),
            recent_published=tuple(summarize(p) for p in published[:RECENT_PUBLISHED]),
        )

    def get(self, row_index: int) -> PostSummary | None:
        post = next((p for p in self._repo.find_all() if p.row_index == row_index), None)
        return summarize(post) if post else None
