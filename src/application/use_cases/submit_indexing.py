"""SubmitIndexingUseCase — 발행 포스트 URL을 Google Indexing API에 크롤링 요청.

API 응답 200은 '요청 접수'일 뿐 색인 완료가 아니다. 색인 여부는 --check-index(URL Inspection)로만
판단하므로 여기서는 시트·상태를 바꾸지 않는다. Indexing API 지원 대상은 JobPosting·
BroadcastEvent(VideoObject) 페이지뿐이라 일반 글에는 기본으로 쓰지 않는다(INDEXING_API_ENABLED).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.domain.ports.post_repository import PostRepository
from src.domain.ports.seo_port import IndexingSubmitPort

logger = logging.getLogger(__name__)


@dataclass
class IndexingSubmitStats:
    """색인 요청 통계. requested는 API가 요청을 받은 건수(색인 완료 아님)."""

    requested: int = 0
    skipped: int = 0
    failed: int = 0


class SubmitIndexingUseCase:
    """발행 완료 포스트의 URL을 Google Indexing API에 크롤링 요청."""

    def __init__(self, repo: PostRepository, indexing_submit: IndexingSubmitPort):
        self._repo = repo
        self._indexing_submit = indexing_submit

    def execute(self, limit: int = 50) -> IndexingSubmitStats:
        stats = IndexingSubmitStats()
        published = self._repo.find_published(limit=limit)

        if not published:
            logger.info("색인 요청 대상 포스트 없음")
            return stats

        for post in published:
            if not post.published_url:
                stats.skipped += 1
                continue

            result = self._indexing_submit.submit(post.published_url)

            if result.success:
                stats.requested += 1
                logger.info(
                    f"크롤링 요청 접수(색인 여부는 --check-index로 확인): "
                    f"{post.keyword} → {post.published_url}"
                )
            else:
                stats.failed += 1
                logger.warning(f"크롤링 요청 실패: {post.keyword} — {result.error}")
                if "quota" in result.error.lower() or "429" in result.error:
                    logger.warning("Indexing API rate limit — 요청 중단")
                    break

        return stats
