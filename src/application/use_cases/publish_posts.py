"""PublishPostsUseCase — Orchestrates the blog post publishing workflow."""
import logging
from dataclasses import dataclass

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.domain.entities.post import Post
from src.domain.exceptions import DailyPublishLimitError
from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.post_repository import PostRepository
from src.domain.services.publish_policy import PublishPolicy
from src.domain.services.quota_manager import QuotaManager

logger = logging.getLogger(__name__)


@dataclass
class PublishStats:
    published: int = 0
    failed: int = 0
    skipped: int = 0


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
        posts = self._repo.find_pending(limit=self._max_posts)

        if not posts:
            logger.info("발행 대기 포스트 없음")
            return stats

        # PublishPolicy로 발행 가능한 포스트만 필터링
        publishable = self._policy.filter_publishable(posts)
        stats.skipped = len(posts) - len(publishable)

        if not publishable:
            logger.info("발행 가능한 포스트 없음 (필터링 후)")
            return stats

        # 쿼터 사전 체크
        published_today = self._repo.count_published_today()
        if not self._quota.can_publish(published_today):
            logger.warning("일일 발행 쿼터 소진 — 발행 건너뜀")
            return stats

        published_posts = self._repo.find_published(limit=50)
        hubs = self._enricher.identify_hubs(published_posts)

        self._browser.start()
        try:
            if not self._browser.login():
                logger.error("로그인 실패 — 발행 중단")
                return stats

            consecutive_failures = 0
            for post in publishable:
                if not self._policy.should_continue_after_failure(
                    consecutive_failures,
                ):
                    logger.warning(
                        f"연속 실패 {consecutive_failures}회 — 발행 중단"
                    )
                    break

                self._enricher.enrich_with_related_links(
                    post, published_posts, hubs,
                )
                self._enricher.attach_internal_link_map(post, published_posts)
                prev_failed = stats.failed
                try:
                    self._publish_single(post, stats)
                    if stats.failed > prev_failed:
                        consecutive_failures += 1
                    else:
                        consecutive_failures = 0
                except DailyPublishLimitError:
                    logger.warning(
                        "일일 발행 제한 도달 — 나머지 포스트 건너뜀 "
                        f"(발행: {stats.published}, 실패: {stats.failed})"
                    )
                    break

        finally:
            self._browser.stop()

        return stats

    def _publish_single(self, post: Post, stats: PublishStats) -> None:
        if not post.is_publishable():
            logger.warning(f"발행 불가 포스트 건너뜀: row={post.row_index}")
            stats.skipped += 1
            return

        try:
            post.mark_publishing()
            self._repo.save(post)

            result = self._browser.publish(post)

            if result.success:
                post.mark_published(result.url, entry_id=result.entry_id)
                stats.published += 1
                logger.info(f"발행 완료: {post.keyword} → {result.url}")
            else:
                post.mark_failed(result.error)
                stats.failed += 1
                logger.error(f"발행 실패: {post.keyword} — {result.error}")

        except DailyPublishLimitError:
            post.reset_to_pending()  # 일일 제한 시 발행대기로 복원
            self._repo.save(post)
            raise
        except Exception as e:
            post.mark_failed(str(e))
            stats.failed += 1
            logger.exception(f"발행 중 예외: {post.keyword}")
        finally:
            self._repo.save(post)
