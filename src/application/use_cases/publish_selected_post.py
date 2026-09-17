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
from src.domain.entities.post import MIN_CONTENT_LENGTH, Post
from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.pipeline_lock_port import PipelineLockPort
from src.domain.ports.post_repository import PostRepository
from src.domain.services.keyword_matcher import find_duplicate
from src.domain.services.quota_manager import QuotaManager
from src.domain.value_objects.post_status import PostStatus

logger = logging.getLogger(__name__)

MIN_QUALITY_SCORE = 70
DUPLICATE_THRESHOLD = 0.7


class ManualPublishOutcome(Enum):
    PUBLISHED = "published"
    FAILED = "failed"
    REJECTED = "rejected"


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
    """발행을 막는 사유 목록 (비어 있으면 발행 가능). 대시보드 표시에도 사용."""
    reasons: list[str] = []
    if post.status != PostStatus.PENDING:
        reasons.append(f"발행대기 상태가 아님 (현재: {post.status.value})")
    body = (post.content.body_markdown or "") if post.content else ""
    if not body.strip():
        reasons.append("본문 없음")
    elif len(body) < MIN_CONTENT_LENGTH:
        reasons.append(f"본문 {len(body)}자 < 최소 {MIN_CONTENT_LENGTH}자")
    if post.quality_score < MIN_QUALITY_SCORE:
        reasons.append(f"품질 점수 {post.quality_score} < {MIN_QUALITY_SCORE}")
    return reasons


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
        post = next((p for p in self._repo.find_all() if p.row_index == row_index), None)
        if post is None:
            return ManualPublishResult.rejected(row_index, f"{row_index}행 게시물을 찾을 수 없음")

        blockers = publish_blockers(post)
        if blockers:
            return ManualPublishResult.rejected(row_index, "발행 불가: " + ", ".join(blockers))

        if not self._quota.can_publish(self._repo.count_published_today()):
            return ManualPublishResult.rejected(row_index, "오늘 발행 쿼터를 모두 사용함")

        published = self._repo.find_published(limit=9999)
        duplicate = self._find_duplicate(post, published)
        if duplicate:
            return ManualPublishResult.rejected(row_index, duplicate)

        if not self._lock.acquire():
            return ManualPublishResult.rejected(
                row_index, "자동 파이프라인이 실행 중 — 끝난 뒤 다시 시도하세요",
            )
        try:
            return self._publish_with_browser(post, published)
        finally:
            self._lock.release()

    @staticmethod
    def _find_duplicate(post: Post, published: list[Post]) -> str:
        keywords = [p.keyword for p in published if p.keyword and p.row_index != post.row_index]
        is_dup, matched, score = find_duplicate(post.keyword, keywords, DUPLICATE_THRESHOLD)
        return f"이미 발행된 키워드와 중복: {matched} ({score:.0%})" if is_dup else ""

    def _publish_with_browser(self, post: Post, published: list[Post]) -> ManualPublishResult:
        self._browser.start()
        try:
            if not self._browser.login():
                return ManualPublishResult.failed(
                    post.row_index, "Tistory 로그인 실패 — 발행대기 유지",
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
        except Exception as e:
            logger.exception(f"수동 발행 중 예외: row={post.row_index}")
            post.mark_failed(f"{type(e).__name__}: {e}")
            self._repo.save(post)
            return ManualPublishResult.failed(post.row_index, post.error_message)
        except BaseException as e:
            post.mark_failed(f"중단: {type(e).__name__}")
            self._repo.save(post)
            raise

        if not result.success:
            post.mark_failed(result.error)
            self._repo.save(post)
            return ManualPublishResult.failed(post.row_index, f"발행 실패: {result.error}")

        post.mark_published(result.url, entry_id=result.entry_id)
        self._repo.save(post)
        logger.info(f"수동 발행 완료: {post.keyword} → {result.url}")
        return ManualPublishResult(
            ManualPublishOutcome.PUBLISHED, post.row_index, "발행 완료", url=result.url,
        )
