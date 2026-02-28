"""PublishPolicy — Domain service for publish eligibility rules."""
from __future__ import annotations

from src.domain.entities.post import Post


class PublishPolicy:
    """Determines which posts are eligible for publishing."""

    def __init__(self, max_posts: int = 5):
        self._max_posts = max_posts

    def filter_publishable(self, posts: list[Post]) -> list[Post]:
        """Return only publishable posts, limited to max_posts."""
        return [p for p in posts if p.is_publishable()][:self._max_posts]

    def should_continue_after_failure(self, consecutive_failures: int) -> bool:
        """Stop after 3 consecutive failures to avoid wasting resources."""
        return consecutive_failures < 3
