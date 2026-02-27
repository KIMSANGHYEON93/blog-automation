"""ResetStuckPostsUseCase — Recovers ghost posts stuck in PUBLISHING status."""
import logging

from src.domain.ports.post_repository import PostRepository

logger = logging.getLogger(__name__)


class ResetStuckPostsUseCase:
    def __init__(self, repo: PostRepository):
        self._repo = repo

    def execute(self) -> int:
        """고스트 포스트를 발행대기로 복구. 복구 건수 반환."""
        stuck_posts = self._repo.find_stuck()
        count = 0
        for post in stuck_posts:
            post.reset_to_pending()
            self._repo.save(post)
            count += 1
            logger.warning(f"고스트 복구: row={post.row_index}, keyword={post.keyword}")
        return count
