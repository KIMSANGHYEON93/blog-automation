"""RevisePostsUseCase — Orchestrates the blog post revision workflow."""
import logging
from dataclasses import dataclass

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.domain.exceptions import DailyPublishLimitError
from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.post_repository import PostRepository

logger = logging.getLogger(__name__)


@dataclass
class ReviseStats:
    revised: int = 0
    failed: int = 0
    skipped: int = 0


class RevisePostsUseCase:
    def __init__(
        self,
        repo: PostRepository,
        browser: BrowserPort,
        enricher: InternalLinkEnricher,
        max_posts: int = 5,
    ):
        self._repo = repo
        self._browser = browser
        self._enricher = enricher
        self._max_posts = max_posts

    def execute(self) -> ReviseStats:
        stats = ReviseStats()
        posts = self._repo.find_revision_pending(limit=self._max_posts)

        if not posts:
            logger.info("수정 대기 포스트 없음")
            return stats

        published_posts = self._repo.find_published(limit=50)
        hubs = self._enricher.identify_hubs(published_posts)

        self._browser.start()
        try:
            if not self._browser.login():
                logger.error("로그인 실패 — 수정 중단")
                return stats

            for post in posts:
                self._enricher.enrich_with_related_links(
                    post, published_posts, hubs,
                )
                self._enricher.attach_internal_link_map(post, published_posts)
                try:
                    self._revise_single(post, stats)
                except DailyPublishLimitError:
                    logger.warning(
                        "일일 발행 제한 도달 — 나머지 포스트 건너뜀 "
                        f"(수정: {stats.revised}, 실패: {stats.failed})"
                    )
                    break

        finally:
            self._browser.stop()

        return stats

    def _revise_single(self, post, stats: ReviseStats) -> None:
        if not post.is_revisable():
            logger.warning(f"수정 불가 포스트 건너뜀: row={post.row_index}")
            stats.skipped += 1
            return

        try:
            post.mark_revising()
            self._repo.save(post)

            result = self._browser.update(post)

            if result.success:
                post.mark_revised(result.url)
                stats.revised += 1
                logger.info(f"수정 완료: {post.keyword} → {result.url}")
            else:
                post.mark_failed(result.error)
                stats.failed += 1
                logger.error(f"수정 실패: {post.keyword} — {result.error}")

        except DailyPublishLimitError:
            post.reset_revising_to_revision_pending()
            self._repo.save(post)
            raise
        except Exception as e:
            post.mark_failed(str(e))
            stats.failed += 1
            logger.exception(f"수정 중 예외: {post.keyword}")
        finally:
            self._repo.save(post)
