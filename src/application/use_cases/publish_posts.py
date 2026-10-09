"""PublishPostsUseCase — Orchestrates the blog post publishing workflow.

배치 규칙 (자동 발행, run_pipeline_b.sh가 .pipeline_b.lock을 잡은 채 실행 — 판단도 잠금 안):
- 시트를 한 번(find_all) 읽어 메모리에서 거른다. 조회 건수와 발행 건수는 따로 제한한다:
  발행대기 전체를 훑고, 브라우저 발행 시도는 max_posts건, 성공은 남은 일일 한도까지.
- 중복: 블로그에 있거나 있을 수 있는 글(claimed_keywords) + 이번 배치에서 앞서 처리한 글과
  비교한다(정확 일치 + 유사도 0.7).
  - 앞 글 발행 성공 또는 결과 불명 → 뒤 글은 보류(사유에 중복 대상 키워드).
  - 앞 글 확실한 실패 → 뒤 글은 이번 실행에서 건너뛰고 발행대기로 둔다(다음 실행 후보).
- 결과 불명(브라우저 호출 중 예외) → 발행실패 + PUBLISH_UNCONFIRMED. 자동 복구 대상이 아니다.
- 플랫폼 한도 응답(예: 티스토리 '최대 15개까지') → 확실히 안 올라갔으므로 발행대기로 되돌리고
  배치를 멈춘다. 앱 쿼터(QuotaManager)는 브라우저를 열기 전에 따로 확인한다.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.domain.entities.post import Post
from src.domain.exceptions import DailyPublishLimitError, LoginFailedError
from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.post_repository import PostRepository
from src.domain.services.error_classifier import ErrorClassifier
from src.domain.services.keyword_matcher import find_duplicate
from src.domain.services.publish_policy import (
    DUPLICATE_THRESHOLD,
    PublishPolicy,
    claimed_keywords,
    duplicate_reason,
)
from src.domain.services.quota_manager import QuotaManager
from src.domain.value_objects.post_status import PostStatus
from src.domain.value_objects.publish_error import PublishErrorType

logger = logging.getLogger(__name__)


@dataclass
class PublishStats:
    published: int = 0
    failed: int = 0
    skipped: int = 0


class _Outcome(Enum):
    PUBLISHED = "published"
    FAILED = "failed"  # 확실한 실패 — 플랫폼이 거부했거나 발행 전 단계에서 멈춤
    UNKNOWN = "unknown"  # 올라갔는지 모름
    PLATFORM_LIMIT = "platform_limit"


def is_platform_limit(error: str) -> bool:
    """브라우저 결과가 플랫폼 일일 한도 거부인지 (앱 쿼터와 별개)."""
    return ErrorClassifier().classify(error).error_type == PublishErrorType.QUOTA_EXCEEDED


class PublishPostsUseCase:
    def __init__(
        self,
        repo: PostRepository,
        browser: BrowserPort,
        enricher: InternalLinkEnricher,
        policy: PublishPolicy,
        quota: QuotaManager,
        max_posts: int = 5,
    ):
        self._repo = repo
        self._browser = browser
        self._enricher = enricher
        self._policy = policy
        self._quota = quota
        self._max_posts = max_posts

    def execute(self) -> PublishStats:
        stats = PublishStats()
        all_posts = self._repo.find_all()
        candidates = self._eligible(all_posts, stats)
        if not candidates:
            return stats

        remaining = self._quota.check_quota(self._repo.count_published_today()).remaining
        if remaining <= 0:
            logger.warning("일일 발행 쿼터 소진 — 발행 건너뜀")
            return stats

        claimed = claimed_keywords(all_posts)
        candidates = self._drop_existing_duplicates(candidates, claimed, stats)
        if not candidates:
            logger.info("중복 제거 후 발행 가능한 포스트 없음")
            return stats

        published_posts = [p for p in all_posts if p.status == PostStatus.PUBLISHED]
        self._browser.start()
        try:
            if not self._browser.login():
                raise LoginFailedError("Tistory 로그인 실패 — 발행 중단")
            self._run_batch(candidates, claimed, published_posts, remaining, stats)
        finally:
            self._browser.stop()
        return stats

    def _eligible(self, all_posts: list[Post], stats: PublishStats) -> list[Post]:
        pending = [p for p in all_posts if p.status == PostStatus.PENDING]
        if not pending:
            logger.info("발행 대기 포스트 없음")
            return []
        eligible: list[Post] = []
        reasons: Counter[str] = Counter()
        for post in pending:
            blockers = post.publish_blockers()
            if blockers:
                reasons.update(re.sub(r"\d+", "N", b) for b in blockers)  # 사유 유형별 통계
                logger.info(f"발행 불가 건너뜀: row={post.row_index} — {', '.join(blockers)}")
            else:
                eligible.append(post)
        stats.skipped += len(pending) - len(eligible)
        logger.info(
            f"발행대기 {len(pending)}건 중 발행 가능 {len(eligible)}건"
            + (f" (불가 사유: {dict(reasons)})" if reasons else "")
        )
        return eligible

    def _drop_existing_duplicates(
        self, candidates: list[Post], claimed: dict[int, str], stats: PublishStats,
    ) -> list[Post]:
        kept: list[Post] = []
        for post in candidates:
            reason = duplicate_reason(post, claimed)
            if reason:
                self._hold(post, reason, stats)
            else:
                kept.append(post)
        return kept

    def _hold(self, post: Post, reason: str, stats: PublishStats) -> None:
        post.mark_hold(reason)
        self._repo.save(post)
        stats.skipped += 1
        logger.warning(f"중복 키워드 → 보류: {post.keyword} ({reason})")

    def _run_batch(
        self, candidates: list[Post], claimed: dict[int, str],
        published_posts: list[Post], remaining: int, stats: PublishStats,
    ) -> None:
        hubs = self._enricher.identify_hubs(published_posts)
        failed_keywords: list[str] = []  # 이번 배치에서 확실히 실패한 글
        attempts = 0
        consecutive_failures = 0
        for post in candidates:
            if stats.published >= remaining or attempts >= self._max_posts:
                logger.info(f"발행 상한 도달 (성공 {stats.published}/{remaining}, 시도 {attempts})")
                break
            if not self._policy.should_continue_after_failure(consecutive_failures):
                logger.warning(f"연속 실패 {consecutive_failures}회 — 발행 중단")
                break
            reason = duplicate_reason(post, claimed)
            if reason:
                self._hold(post, reason, stats)
                continue
            if find_duplicate(post.keyword, failed_keywords, DUPLICATE_THRESHOLD)[0]:
                logger.info(f"같은 배치의 실패 글과 중복 — 다음 실행으로 미룸: {post.keyword}")
                stats.skipped += 1
                continue

            self._enricher.enrich_with_related_links(post, published_posts, hubs)
            self._enricher.attach_internal_link_map(post, published_posts)
            attempts += 1
            outcome = self._publish_single(post, stats)
            if outcome == _Outcome.PLATFORM_LIMIT:
                logger.warning(
                    "플랫폼 일일 발행 제한 도달 — 나머지 포스트 건너뜀 "
                    f"(발행: {stats.published}, 실패: {stats.failed})"
                )
                break
            if outcome in (_Outcome.PUBLISHED, _Outcome.UNKNOWN):
                claimed[post.row_index] = post.keyword
            else:
                failed_keywords.append(post.keyword)
            consecutive_failures = 0 if outcome == _Outcome.PUBLISHED else consecutive_failures + 1

    def _publish_single(self, post: Post, stats: PublishStats) -> _Outcome:
        post.mark_publishing()
        # 고스트 복구 때 관리자가 블로그에서 찾아볼 시각 단서
        post.error_message = f"발행 시도 {datetime.now():%Y-%m-%d %H:%M:%S}"
        self._repo.save(post)  # 실패하면 시트는 발행대기 그대로 — 브라우저 호출 전이라 안전

        try:
            result = self._browser.publish(post)
        except DailyPublishLimitError as e:
            return self._back_to_pending(post, f"플랫폼 일일 한도: {e}")
        except Exception as e:
            logger.exception(f"발행 중 예외 — 결과 불명: {post.keyword}")
            post.mark_publish_unconfirmed(f"{type(e).__name__}: {e}")
            stats.failed += 1
            self._repo.save(post)
            return _Outcome.UNKNOWN
        except BaseException as e:
            post.mark_publish_unconfirmed(f"중단: {type(e).__name__}")
            self._repo.save(post)
            raise

        if result.success:
            post.mark_published(result.url, entry_id=result.entry_id)
            self._save_published(post)
            stats.published += 1
            logger.info(f"발행 완료: {post.keyword} → {result.url}")
            return _Outcome.PUBLISHED
        if is_platform_limit(result.error):
            return self._back_to_pending(post, f"플랫폼 일일 한도: {result.error}")
        post.mark_failed(result.error)
        stats.failed += 1
        self._repo.save(post)
        logger.error(f"발행 실패: {post.keyword} — {result.error}")
        return _Outcome.FAILED

    def _back_to_pending(self, post: Post, reason: str) -> _Outcome:
        post.reset_to_pending()
        post.error_message = reason[:200]
        self._repo.save(post)
        return _Outcome.PLATFORM_LIMIT

    def _save_published(self, post: Post) -> None:
        """외부 발행은 끝났다. 저장이 끝내 실패하면 시트에 '발행중'이 남고, 다음 고스트 복구가
        '발행 여부 수동 확인 필요'로 돌려 자동 재발행을 막는다. 주소는 로그에 남긴다."""
        try:
            self._repo.save(post)
        except Exception:
            logger.warning(f"발행완료 저장 실패 — 1회 재시도: row={post.row_index}")
            try:
                self._repo.save(post)
            except Exception:
                logger.error(
                    f"발행은 됐지만 시트 기록 실패: row={post.row_index}, "
                    f"keyword={post.keyword}, url={post.published_url}, entry_id={post.entry_id}"
                )
                raise
