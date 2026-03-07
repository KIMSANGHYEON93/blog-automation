"""SubmitIndexingUseCase — 발행 포스트의 Google 색인 제출."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.domain.entities.post import Post
from src.domain.ports.post_repository import PostRepository
from src.domain.ports.seo_port import IndexingSubmitPort
from src.domain.value_objects.post_status import PostStatus

logger = logging.getLogger(__name__)


@dataclass
class IndexingSubmitStats:
    """색인 제출 통계."""

    submitted: int = 0
    skipped: int = 0
    failed: int = 0


class SubmitIndexingUseCase:
    """발행 완료 포스트의 URL을 Google Indexing API에 제출."""

    def __init__(self, repo: PostRepository, indexing_submit: IndexingSubmitPort):
        self._repo = repo
        self._indexing_submit = indexing_submit

    def execute(self, limit: int = 50) -> IndexingSubmitStats:
        stats = IndexingSubmitStats()
        published = self._repo.find_published(limit=limit)

        if not published:
            logger.info("색인 제출 대상 포스트 없음")
            return stats

        for post in published:
            if not post.published_url:
                stats.skipped += 1
                continue

            result = self._indexing_submit.submit(post.published_url)

            if result.success:
                stats.submitted += 1
                logger.info(f"색인 제출 완료: {post.keyword} → {post.published_url}")
            else:
                stats.failed += 1
                logger.warning(
                    f"색인 제출 실패: {post.keyword} — {result.error}"
                )
                if "quota" in result.error.lower() or "429" in result.error:
                    logger.warning("Indexing API rate limit — 색인 제출 중단")
                    break

        return stats

    def submit_single(self, post: Post) -> bool:
        """단일 포스트 색인 제출 (발행 직후 호출용).

        Returns:
            True if submitted successfully.
        """
        if post.status != PostStatus.PUBLISHED or not post.published_url:
            return False

        result = self._indexing_submit.submit(post.published_url)
        if result.success:
            logger.info(f"색인 즉시 제출: {post.keyword} → {post.published_url}")
        else:
            logger.warning(f"색인 즉시 제출 실패: {post.keyword} — {result.error}")
        return result.success
