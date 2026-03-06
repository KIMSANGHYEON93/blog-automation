"""PublishPostsUseCase — Orchestrates the blog post publishing workflow."""
import logging
from dataclasses import dataclass, replace

from src.domain.entities.post import Post
from src.domain.exceptions import DailyPublishLimitError
from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.post_repository import PostRepository
from src.domain.services.internal_link_service import InternalLinkService

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
        self._link_service = InternalLinkService()

    def execute(self) -> PublishStats:
        stats = PublishStats()
        posts = self._repo.find_pending(limit=self._max_posts)

        if not posts:
            logger.info("발행 대기 포스트 없음")
            return stats

        published_posts = self._repo.find_published(limit=50)
        hubs = self._link_service.identify_hubs(published_posts)

        self._browser.start()
        try:
            if not self._browser.login():
                logger.error("로그인 실패 — 발행 중단")
                return stats

            for post in posts:
                self._enrich_with_related_links(post, published_posts, hubs)
                self._attach_internal_link_map(post, published_posts)
                try:
                    self._publish_single(post, stats)
                except DailyPublishLimitError:
                    logger.warning(
                        "일일 발행 제한 도달 — 나머지 포스트 건너뜀 "
                        f"(발행: {stats.published}, 실패: {stats.failed})"
                    )
                    break

        finally:
            self._browser.stop()

        return stats

    def _enrich_with_related_links(
        self, post: Post, published: list[Post], hubs: list[Post],
    ) -> None:
        if not post.content or not post.content.has_body():
            return

        related = self._link_service.select_links(post, published, hubs)
        if not related:
            return

        items = "".join(
            f'<li style="margin:8px 0;">'
            f'<a href="{p.published_url}">{p.keyword}</a></li>'
            for p in related[:5]
        )
        html = (
            "\n\n<hr>\n"
            '<div style="margin-top:30px;padding:20px;'
            'background:#f8f9fa;border-radius:8px;">'
            "<h3>관련 글</h3>"
            f'<ul style="list-style:none;padding:0;">{items}</ul>'
            "</div>"
        )
        post.content = replace(
            post.content, body_markdown=post.content.body_markdown + html,
        )

    def _attach_internal_link_map(
        self, post: Post, published: list[Post],
    ) -> None:
        """발행 완료 포스트의 keyword→URL 매핑을 post에 첨부.

        tistory_editor가 HTML 변환 후 inject_internal_links()에 전달한다.
        """
        if not post.content or not post.content.has_body():
            return
        link_map = {
            p.keyword: p.published_url
            for p in published
            if p.keyword and p.published_url
            and p.row_index != post.row_index
        }
        if link_map:
            post._internal_link_map = link_map  # noqa: SLF001

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
