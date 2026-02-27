"""Post — Aggregate Root entity with state machine."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.domain.value_objects.post_status import PostStatus
from src.domain.value_objects.post_content import PostContent
from src.domain.exceptions import InvalidStatusTransition


@dataclass
class Post:
    row_index: int
    keyword: str
    category: str = ""
    content: Optional[PostContent] = None
    status: PostStatus = PostStatus.PENDING
    published_url: str = ""
    published_at: Optional[datetime] = None
    error_message: str = ""

    def mark_publishing(self) -> None:
        """PENDING → PUBLISHING (only from PENDING)."""
        if self.status != PostStatus.PENDING:
            raise InvalidStatusTransition(self.status, PostStatus.PUBLISHING)
        self.status = PostStatus.PUBLISHING

    def mark_published(self, url: str) -> None:
        """PUBLISHING → PUBLISHED with URL and timestamp."""
        self.status = PostStatus.PUBLISHED
        self.published_url = url
        self.published_at = datetime.now()

    def mark_failed(self, reason: str) -> None:
        """PUBLISHING → FAILED with reason (truncated to 200 chars)."""
        self.status = PostStatus.FAILED
        self.error_message = reason[:200]

    def reset_to_pending(self) -> None:
        """Ghost recovery: PUBLISHING → PENDING."""
        if self.status != PostStatus.PUBLISHING:
            return
        self.status = PostStatus.PENDING
        self.error_message = "이전 실행 중단으로 자동 복구됨"

    def is_publishable(self) -> bool:
        """True only when PENDING + content has body."""
        return (
            self.status == PostStatus.PENDING
            and self.content is not None
            and self.content.has_body()
        )
