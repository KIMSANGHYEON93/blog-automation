"""CheckIndexingUseCase — 발행 포스트의 Google 색인 상태 점검.

색인되지 않은 포스트를 수정대기(REVISION_PENDING) 상태로 전환.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.entities.post import Post
from src.domain.ports.post_repository import PostRepository
from src.domain.ports.seo_port import IndexingPort, IndexingResult
from src.domain.value_objects.post_status import PostStatus

logger = logging.getLogger(__name__)

# 발행·수정 뒤 이 기간 안에는 색인 점검을 하지 않는다 — 구글 수집은 며칠~몇 주 걸린다
REINDEX_GRACE = timedelta(days=14)


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

    def __init__(
        self, repo: PostRepository, indexing: IndexingPort,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self._repo = repo
        self._indexing = indexing
        self._clock = clock

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

        # 수정하면 published_at이 지금으로 바뀐다(mark_revised). 구글이 다시 수집할 시간을 주지 않고
        # 매일 점검하면 같은 글을 매일 수정하는 순환이 생긴다(2026-09-27~10-01 실측)
        if post.published_at and self._clock() - post.published_at < REINDEX_GRACE:
            logger.info(f"최근 발행·수정 — 색인 점검 건너뜀: {post.keyword}")
            return IndexingCheckResult(
                success=False, post_keyword=post.keyword, url=post.published_url,
                is_indexed=False,
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
