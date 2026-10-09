"""ReviseSelectedPostUseCase — 대시보드에서 고친 발행 글 1건을 같은 URL에서 수정 발행.

수정은 같은 글을 덮어쓰므로 여러 번 해도 중복이 생기지 않는다. 그래서 실패하면 발행실패로
빼지 않고 수정대기로 되돌려 사유만 남긴다 — 관리자가 바로 다시 시도할 수 있게.
"""
from __future__ import annotations

import logging

from src.application.use_cases.publish_selected_post import (
    LOGIN_FAILED,
    ManualPublishOutcome,
    ManualPublishResult,
)
from src.domain.entities.post import Post
from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.pipeline_lock_port import PipelineLockPort
from src.domain.ports.post_repository import PostRepository

logger = logging.getLogger(__name__)


class ReviseSelectedPostUseCase:
    def __init__(self, repo: PostRepository, browser: BrowserPort, lock: PipelineLockPort):
        self._repo = repo
        self._browser = browser
        self._lock = lock

    def execute(self, row_index: int) -> ManualPublishResult:
        if not self._lock.acquire():
            return ManualPublishResult.rejected(
                row_index, "다른 작업(자동 발행 등)이 실행 중 — 끝난 뒤 다시 시도하세요",
            )
        try:
            # 잠금 뒤에 읽는다 — 그 사이 자동 수정이 끝냈을 수 있다
            post = next((p for p in self._repo.find_all() if p.row_index == row_index), None)
            if post is None or not post.is_revisable():
                return ManualPublishResult.rejected(
                    row_index,
                    "수정대기 상태이고 본문과 글 번호가 있는 글만 수정 발행할 수 있습니다"
                    + (f" ({', '.join(post.revision_blockers())})" if post else ""),
                )
            self._browser.start()
            try:
                if not self._browser.login():
                    return ManualPublishResult.failed(row_index, f"{LOGIN_FAILED} — 수정대기 유지")
                return self._revise(post)
            finally:
                self._browser.stop()
        finally:
            self._lock.release()

    def _revise(self, post: Post) -> ManualPublishResult:
        post.mark_revising()
        self._repo.save(post)
        try:
            result = self._browser.update(post)
            error = "" if result.success else result.error
        except Exception as e:
            logger.exception(f"수정 발행 중 예외: row={post.row_index}")
            error = f"{type(e).__name__}: {e}"
        except BaseException as e:
            self._back_to_pending(post, f"중단: {type(e).__name__}")
            raise
        if error:
            self._back_to_pending(post, f"수정 실패: {error}")
            return ManualPublishResult.failed(post.row_index, post.error_message)

        post.mark_revised(result.url)  # 첫 발행일 유지, 수정 시각·횟수는 따로 기록
        message = "수정 발행 완료"
        post.error_message = ""
        if result.warnings:
            post.error_message = f"수정 후 점검: {'; '.join(result.warnings)}"[:200]
            message += f" — 점검 경고 {len(result.warnings)}건: {'; '.join(result.warnings)}"
        self._repo.save(post)
        logger.info(f"수정 발행 완료: {post.keyword} → {result.url}")
        return ManualPublishResult(
            ManualPublishOutcome.REVISED, post.row_index, message, url=result.url,
        )

    def _back_to_pending(self, post: Post, reason: str) -> None:
        post.mark_failed(reason)
        post.reset_failed_to_revision_pending()
        post.error_message = reason[:200]
        self._repo.save(post)
