"""ResetStuckPostsUseCase — Recovers ghost posts stuck in PUBLISHING status."""
import logging

from src.domain.ports.post_repository import PostRepository

logger = logging.getLogger(__name__)


class ResetStuckPostsUseCase:
    def __init__(self, repo: PostRepository, retry_failed: bool = False):
        self._repo = repo
        self._retry_failed = retry_failed

    def execute(self) -> int:
        """고스트 포스트를 발행대기로 복구. 복구 건수 반환."""
        stuck_posts = self._repo.find_stuck()
        count = 0
        for post in stuck_posts:
            post.reset_to_pending()
            self._repo.save(post)
            count += 1
            logger.warning(f"고스트 복구: row={post.row_index}, keyword={post.keyword}")

        # 실패 포스트 재시도 (옵트인)
        if self._retry_failed:
            failed_posts = self._repo.find_failed()
            for post in failed_posts:
                post.reset_failed_to_pending()
                self._repo.save(post)
                count += 1
                logger.warning(f"실패 재시도: row={post.row_index}, keyword={post.keyword}")

        return count
