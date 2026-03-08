"""RevisePostsUseCase — Orchestrates the blog post revision workflow."""
import logging
from dataclasses import dataclass, replace

from src.domain.entities.post import Post
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
    def __init__(self, repo: PostRepository, browser: BrowserPort,
                 max_posts: int = 5):
        self._repo = repo
        self._browser = browser
        self._max_posts = max_posts

    def execute(self) -> ReviseStats:
        stats = ReviseStats()
        posts = self._repo.find_revision_pending(limit=self._max_posts)

        if not posts:
            logger.info("수정 대기 포스트 없음")
            return stats

        published_posts = self._repo.find_published(limit=50)

        self._browser.start()
        try:
            if not self._browser.login():
                logger.error("로그인 실패 — 수정 중단")
                return stats

            for post in posts:
                self._enrich_with_related_links(post, published_posts)
                self._attach_internal_link_map(post, published_posts)
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

    def _enrich_with_related_links(
        self, post: Post, published: list[Post],
    ) -> None:
        if not post.content or not post.content.has_body():
            return

        same_cat = [
            p for p in published
            if p.category == post.category
            and p.row_index != post.row_index
            and p.published_url
        ]
        diff_cat = [
            p for p in published
            if p.category != post.category
            and p.row_index != post.row_index
            and p.published_url
        ]
        related = same_cat[:3] + diff_cat[: max(0, 5 - len(same_cat[:3]))]
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
            post.content, body_markdown=(post.content.body_markdown or "") + html,
        )

    def _attach_internal_link_map(
        self, post: Post, published: list[Post],
    ) -> None:
        if not post.content or not post.content.has_body():
            return
        link_map = {
            p.keyword: p.published_url
            for p in published
            if p.keyword and p.published_url
            and p.row_index != post.row_index
        }
        if link_map:
            post.internal_link_map = link_map

    def _revise_single(self, post: Post, stats: ReviseStats) -> None:
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
