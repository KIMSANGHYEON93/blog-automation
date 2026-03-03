"""CheckCwvUseCase — 발행 포스트의 Core Web Vitals 점검."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.domain.entities.post import Post
from src.domain.ports.post_repository import PostRepository
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.seo.cwv_checker import CwvResult, check_cwv

logger = logging.getLogger(__name__)


@dataclass
class CwvCheckResult:
    """CWV 점검 결과 DTO."""

    success: bool
    post_keyword: str
    url: str
    lcp: float
    cls: float
    score: int
    passed: bool
    error: str = ""


class CheckCwvUseCase:
    """발행 완료 포스트의 CWV를 측정하고 시트에 기록."""

    def __init__(self, repo: PostRepository):
        self._repo = repo

    def execute(self, post: Post) -> CwvCheckResult:
        # 1. PUBLISHED 상태 검증
        if post.status != PostStatus.PUBLISHED:
            return CwvCheckResult(
                success=False,
                post_keyword=post.keyword,
                url=post.published_url,
                lcp=0.0,
                cls=0.0,
                score=0,
                passed=False,
                error=f"발행완료 상태가 아닙니다: {post.status.value}",
            )

        if not post.published_url:
            return CwvCheckResult(
                success=False,
                post_keyword=post.keyword,
                url="",
                lcp=0.0,
                cls=0.0,
                score=0,
                passed=False,
                error="발행 URL이 없습니다",
            )

        # 2. CWV 측정
        cwv: CwvResult = check_cwv(post.published_url)

        if cwv.error:
            return CwvCheckResult(
                success=False,
                post_keyword=post.keyword,
                url=post.published_url,
                lcp=0.0,
                cls=0.0,
                score=0,
                passed=False,
                error=cwv.error,
            )

        # 3. 시트 저장
        self._repo.save_cwv_record(
            row_index=post.row_index,
            lcp=cwv.lcp_seconds,
            cls_score=cwv.cls_score,
        )

        logger.info(
            f"CWV 점검 완료: {post.keyword} | "
            f"LCP={cwv.lcp_seconds}s, CLS={cwv.cls_score}, "
            f"Score={cwv.performance_score}, Passed={cwv.passed}"
        )

        # 4. 결과 반환
        return CwvCheckResult(
            success=True,
            post_keyword=post.keyword,
            url=post.published_url,
            lcp=cwv.lcp_seconds,
            cls=cwv.cls_score,
            score=cwv.performance_score,
            passed=cwv.passed,
        )
