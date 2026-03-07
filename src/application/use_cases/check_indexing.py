"""CheckIndexingUseCase — 발행 포스트의 Google 색인 상태 점검.

색인되지 않은 포스트를 수정대기(REVISION_PENDING) 상태로 전환.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.domain.entities.post import Post
from src.domain.ports.post_repository import PostRepository
from src.domain.ports.seo_port import IndexingPort, IndexingResult
from src.domain.value_objects.post_status import PostStatus

logger = logging.getLogger(__name__)


@dataclass
class IndexingCheckResult:
    """색인 점검 결과 DTO."""

    success: bool
    post_keyword: str
    url: str
    is_indexed: bool
    verdict: str = ""
    coverage_state: str = ""
    marked_revision: bool = False
    error: str = ""


@dataclass
class IndexingCheckStats:
    """색인 점검 전체 통계."""

    checked: int = 0
    indexed: int = 0
    not_indexed: int = 0
    marked_revision: int = 0
    errors: int = 0


class CheckIndexingUseCase:
    """발행 완료 포스트의 Google 색인 상태를 점검하고,
    색인되지 않은 포스트를 수정대기로 전환."""

    def __init__(self, repo: PostRepository, indexing: IndexingPort):
        self._repo = repo
        self._indexing = indexing

    def execute(self, post: Post) -> IndexingCheckResult:
        """단일 포스트의 색인 상태 점검."""
        if post.status != PostStatus.PUBLISHED:
            return IndexingCheckResult(
                success=False,
                post_keyword=post.keyword,
                url=post.published_url,
                is_indexed=False,
                error=f"발행완료 상태가 아닙니다: {post.status.value}",
            )

        if not post.published_url:
            return IndexingCheckResult(
                success=False,
                post_keyword=post.keyword,
                url="",
                is_indexed=False,
                error="발행 URL이 없습니다",
            )

        result: IndexingResult = self._indexing.check(post.published_url)

        if result.error:
            return IndexingCheckResult(
                success=False,
                post_keyword=post.keyword,
                url=post.published_url,
                is_indexed=False,
                error=result.error,
            )

        marked = False
        if not result.is_indexed:
            reason = (
                f"색인 미생성: {result.coverage_state or result.verdict}"
            )
            post.mark_revision_pending(reason)
            self._repo.save(post)
            marked = True
            logger.info(
                f"색인 미생성 → 수정대기: {post.keyword} "
                f"({result.coverage_state})"
            )

        return IndexingCheckResult(
            success=True,
            post_keyword=post.keyword,
            url=post.published_url,
            is_indexed=result.is_indexed,
            verdict=result.verdict,
            coverage_state=result.coverage_state,
            marked_revision=marked,
        )
