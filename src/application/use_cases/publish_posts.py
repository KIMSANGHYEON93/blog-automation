"""PublishPostsUseCase — Orchestrates the blog post publishing workflow."""
import logging
from dataclasses import dataclass

from src.domain.entities.post import Post
from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.post_repository import PostRepository

logger = logging.getLogger(__name__)


@dataclass
class PublishStats:
    published: int = 0
    failed: int = 0
    skipped: int = 0


class PublishPostsUseCase:
    def __init__(self, repo: PostRepository, browser: BrowserPort,
                 max_posts: int = 5):
        self._repo = repo
        self._browser = browser
        self._max_posts = max_posts

    def execute(self) -> PublishStats:
        stats = PublishStats()
        posts = self._repo.find_pending(limit=self._max_posts)

        if not posts:
            logger.info("발행 대기 포스트 없음")
            return stats

        self._browser.start()
        try:
            if not self._browser.login():
                logger.error("로그인 실패 — 발행 중단")
                return stats

            for post in posts:
                self._publish_single(post, stats)

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
                post.mark_published(result.url)
                stats.published += 1
                logger.info(f"발행 완료: {post.keyword} → {result.url}")
            else:
                post.mark_failed(result.error)
                stats.failed += 1
                logger.error(f"발행 실패: {post.keyword} — {result.error}")

        except Exception as e:
            post.mark_failed(str(e))
            stats.failed += 1
            logger.exception(f"발행 중 예외: {post.keyword}")
        finally:
            self._repo.save(post)
