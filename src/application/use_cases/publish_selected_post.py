"""PublishSelectedPostUseCase — 관리자가 대시보드에서 선택한 게시물 1건 수동 발행.

자동 발행(PublishPostsUseCase)과 같은 규칙(발행 가능 조건, 일일 쿼터, 중복 키워드,
내부 링크)을 적용하되, 관리자의 명시적 선택이므로 거부 시 게시물 상태를 바꾸지 않는다.
자동 파이프라인과 같은 브라우저 프로필을 쓰므로 PipelineLockPort로 동시 실행을 막는다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.application.use_cases.publish_posts import is_platform_limit
from src.domain.entities.post import (  # noqa: F401 — 기존 import 경로 유지
    EXPERIENCE_PLACEHOLDER,
    MIN_QUALITY_SCORE,
    Post,
)
from src.domain.exceptions import DailyPublishLimitError
from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.pipeline_lock_port import PipelineLockPort
from src.domain.ports.post_repository import PostRepository
from src.domain.services.publish_policy import (  # noqa: F401
    DUPLICATE_THRESHOLD,
    claimed_keywords,
    duplicate_reason,
)
from src.domain.services.quota_manager import QuotaManager
from src.domain.value_objects.post_status import PostStatus

logger = logging.getLogger(__name__)

LOGIN_FAILED = "로그인 실패"


class ManualPublishOutcome(Enum):
    PUBLISHED = "published"
    FAILED = "failed"
    REJECTED = "rejected"
    DRAFTED = "drafted"  # 임시저장 시험만 함 — 시트 상태는 바뀌지 않는다
    GENERATED = "generated"  # 대시보드 '지금 생성'(n8n 실행) 성공
    REVISED = "revised"  # 발행된 글을 같은 URL에서 수정 발행
    LOGGED_IN = "logged_in"  # 대시보드 '다시 로그인'(네이버·카카오톡) 성공


@dataclass(frozen=True)
class ManualPublishResult:
    outcome: ManualPublishOutcome
    row_index: int
    message: str
    url: str = ""

    @classmethod
    def rejected(cls, row_index: int, message: str) -> ManualPublishResult:
        return cls(ManualPublishOutcome.REJECTED, row_index, message)

    @classmethod
    def failed(cls, row_index: int, message: str) -> ManualPublishResult:
        return cls(ManualPublishOutcome.FAILED, row_index, message)


def publish_blockers(post: Post) -> list[str]:
    """발행을 막는 사유 목록 (비어 있으면 발행 가능). 자동 발행과 같은 Post.publish_blockers."""
    return post.publish_blockers()


class PublishSelectedPostUseCase:
    def __init__(
        self,
        repo: PostRepository,
        browser: BrowserPort,
        enricher: InternalLinkEnricher,
        quota: QuotaManager,
        lock: PipelineLockPort,
    ):
        self._repo = repo
        self._browser = browser
        self._enricher = enricher
        self._quota = quota
        self._lock = lock

    def execute(self, row_index: int) -> ManualPublishResult:
        # 잠금을 먼저 잡고 시트를 읽는다 — 잠금 전에 읽은 상태·쿼터·중복 판단은 그 사이
        # 자동 실행이 바꿨을 수 있다(오래된 판단으로 발행하지 않기)
        if not self._lock.acquire():
            return ManualPublishResult.rejected(
                row_index, "자동 파이프라인이 실행 중 — 끝난 뒤 다시 시도하세요",
            )
        try:
            return self._execute_locked(row_index)
        finally:
            self._lock.release()

    def _execute_locked(self, row_index: int) -> ManualPublishResult:
        all_posts = self._repo.find_all()
        post = next((p for p in all_posts if p.row_index == row_index), None)
        if post is None:
            return ManualPublishResult.rejected(row_index, f"{row_index}행 게시물을 찾을 수 없음")

        blockers = publish_blockers(post)
        if blockers:
            return ManualPublishResult.rejected(row_index, "발행 불가: " + ", ".join(blockers))

        if not self._quota.can_publish(self._repo.count_published_today()):
            return ManualPublishResult.rejected(row_index, "오늘 발행 쿼터를 모두 사용함")

        duplicate = duplicate_reason(post, claimed_keywords(all_posts))
        if duplicate:
            return ManualPublishResult.rejected(
                row_index, f"이미 발행(또는 발행 시도)된 글과 {duplicate}",
            )

        published = [p for p in all_posts if p.status == PostStatus.PUBLISHED]
        return self._publish_with_browser(post, published)

    def _publish_with_browser(self, post: Post, published: list[Post]) -> ManualPublishResult:
        self._browser.start()
        try:
            if not self._browser.login():
                return ManualPublishResult.failed(
                    post.row_index, f"{LOGIN_FAILED} — 발행대기 유지",
                )
            self._enricher.enrich_with_related_links(
                post, published, self._enricher.identify_hubs(published),
            )
            self._enricher.attach_internal_link_map(post, published)
            return self._publish(post)
        finally:
            self._browser.stop()

    def _publish(self, post: Post) -> ManualPublishResult:
        post.mark_publishing()
        self._repo.save(post)
        try:
            result = self._browser.publish(post)
        except DailyPublishLimitError as e:
            return self._keep_pending(post, f"플랫폼 일일 한도: {e}")
        except Exception as e:
            # 브라우저가 어디서 멈췄는지 모른다 — 올라갔을 수 있으니 재발행 금지 표시
            logger.exception(f"수동 발행 중 예외 — 결과 불명: row={post.row_index}")
            post.mark_publish_unconfirmed(f"{type(e).__name__}: {e}")
            self._repo.save(post)
            return ManualPublishResult.failed(post.row_index, post.error_message)
        except BaseException as e:
            post.mark_publish_unconfirmed(f"중단: {type(e).__name__}")
            self._repo.save(post)
            raise

        if not result.success and is_platform_limit(result.error):
            return self._keep_pending(post, f"플랫폼 일일 한도: {result.error}")
        if not result.success:
            post.mark_failed(result.error)
            self._repo.save(post)
            return ManualPublishResult.failed(post.row_index, f"발행 실패: {result.error}")

        post.mark_published(result.url, entry_id=result.entry_id)
        message = "발행 완료"
        if result.warnings:
            # 발행은 됐다 — 상태는 발행완료로 두고, 고칠 거리를 시트 오류 열과 결과에 남긴다
            post.error_message = f"발행 후 점검: {'; '.join(result.warnings)}"[:200]
            message += f" — 점검 경고 {len(result.warnings)}건: {'; '.join(result.warnings)}"
        self._repo.save(post)
        logger.info(f"수동 발행 완료: {post.keyword} → {result.url}")
        return ManualPublishResult(
            ManualPublishOutcome.PUBLISHED, post.row_index, message, url=result.url,
        )

    def _keep_pending(self, post: Post, reason: str) -> ManualPublishResult:
        """플랫폼이 거부했다 — 확실히 안 올라갔으므로 발행대기로 되돌린다."""
        post.reset_to_pending()
        post.error_message = reason[:200]
        self._repo.save(post)
        return ManualPublishResult.failed(post.row_index, f"{reason} — 발행대기 유지")
