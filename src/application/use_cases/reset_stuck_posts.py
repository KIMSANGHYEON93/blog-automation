"""ResetStuckPostsUseCase — 중간에 끊긴 실행이 남긴 '발행중'·'수정중' 글 정리.

- 발행중: 시트는 브라우저 발행 직전에 '발행중'으로 바뀐다. 남아 있다면 발행이 됐는지 모른다
  (발행 성공 후 시트 저장만 실패했을 수도 있다). 발행대기로 되돌리면 같은 글이 또 올라가므로
  발행실패 + '발행 여부 수동 확인 필요'로 돌리고 자동 복구·재시도 대상에서 뺀다.
  확인 수단(BrowserPort의 조회 기능)이 없으므로 정확히 한 번 발행을 보장하지는 않는다 —
  중복 대신 사람 확인을 택한다.
- 수정중: 같은 글을 덮어쓰는 작업이라 다시 해도 중복이 없다 → 수정대기로 되돌린다.
"""
from __future__ import annotations

import logging

from src.domain.ports.post_repository import PostRepository
from src.domain.services.retry_policy import RetryPolicy

logger = logging.getLogger(__name__)


class ResetStuckPostsUseCase:
    def __init__(
        self,
        repo: PostRepository,
        retry_failed: bool = False,
        retry_policy: RetryPolicy | None = None,
    ):
        self._repo = repo
        self._retry_failed = retry_failed
        self._retry_policy = retry_policy or RetryPolicy()

    def execute(self) -> int:
        """고스트 정리 건수 반환."""
        stuck_posts = self._repo.find_stuck()
        count = 0
        for post in stuck_posts:
            when = post.error_message or "시각 미상"
            post.mark_publish_unconfirmed(f"발행중에 중단됨({when}) — 블로그에서 확인 후 되돌리기")
            self._repo.save(post)
            count += 1
            logger.error(
                f"발행 결과 불명 → 관리자 확인 필요: row={post.row_index}, keyword={post.keyword}"
            )

        # 수정중 고스트 복구 (REVISING → REVISION_PENDING)
        revising_stuck = self._repo.find_revising_stuck()
        for post in revising_stuck:
            post.reset_revising_to_revision_pending()
            self._repo.save(post)
            count += 1
            logger.warning(
                f"수정중 고스트 복구: row={post.row_index}, keyword={post.keyword}"
            )

        # 실패 포스트 재시도 (옵트인 + RetryPolicy 적용)
        if self._retry_failed:
            failed_posts = self._repo.find_failed()
            for post in failed_posts:
                if post.is_publish_unconfirmed():
                    continue  # 이미 올라갔을 수 있다 — 사람이 확인해야 한다
                if not self._retry_policy.is_eligible(
                    post.retry_count, post.next_retry_at,
                ):
                    logger.info(
                        f"재시도 불가 (max={self._retry_policy.max_retries}, "
                        f"count={post.retry_count}): "
                        f"row={post.row_index}, keyword={post.keyword}"
                    )
                    continue
                post.retry_count += 1
                post.next_retry_at = self._retry_policy.calculate_next_retry(
                    post.retry_count,
                )
                post.reset_failed_to_pending()
                self._repo.save(post)
                count += 1
                logger.warning(
                    f"실패 재시도 ({post.retry_count}/{self._retry_policy.max_retries}): "
                    f"row={post.row_index}, keyword={post.keyword}"
                )

        return count
