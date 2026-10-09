"""PublishPolicy — Domain service for publish eligibility rules."""
from __future__ import annotations

from src.domain.entities.post import Post
from src.domain.services.keyword_matcher import find_duplicate

# 정확 일치 + 토큰 유사도 0.7 이상을 같은 주제로 본다(자동·수동 발행 공통)
DUPLICATE_THRESHOLD = 0.7


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


def claimed_keywords(posts: list[Post]) -> dict[int, str]:
    """블로그에 올라가 있거나 올라갔을 수 있는 글의 {행: 키워드}.

    발행완료뿐 아니라 발행중·수정 중·결과 불명 실패도 넣는다 — 이미 올라갔을 수 있는 글과
    같은 키워드를 또 발행하면 중복 글이 된다.
    """
    return {p.row_index: p.keyword for p in posts if p.keyword and p.may_be_on_blog()}


def duplicate_reason(post: Post, claimed: dict[int, str]) -> str:
    """claimed 중 post와 같은 주제가 있으면 사유(중복 대상 키워드 포함), 없으면 빈 문자열."""
    others = [kw for row, kw in claimed.items() if row != post.row_index]
    is_dup, matched, score = find_duplicate(post.keyword, others, DUPLICATE_THRESHOLD)
    return f"중복: {matched} ({score:.0%})" if is_dup else ""
