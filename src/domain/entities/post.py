"""Post — Aggregate Root entity with state machine."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.exceptions import InvalidStatusTransitionError
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus


@dataclass
class Post:
    row_index: int
    keyword: str
    category: str = ""
    content: PostContent | None = None
    status: PostStatus = PostStatus.PENDING
    published_url: str = ""
    published_at: datetime | None = None
    error_message: str = ""
    entry_id: str = ""

    def mark_publishing(self) -> None:
        """PENDING → PUBLISHING (only from PENDING)."""
        if self.status != PostStatus.PENDING:
            raise InvalidStatusTransitionError(self.status, PostStatus.PUBLISHING)
        self.status = PostStatus.PUBLISHING

    def mark_published(self, url: str, entry_id: str = "") -> None:
        """PUBLISHING → PUBLISHED with URL and timestamp."""
        self.status = PostStatus.PUBLISHED
        self.published_url = url
        self.published_at = datetime.now()
        if entry_id:
            self.entry_id = entry_id

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

    def reset_failed_to_pending(self) -> None:
        """Retry recovery: FAILED → PENDING. 비-FAILED에서 호출 시 에러."""
        if self.status != PostStatus.FAILED:
            raise InvalidStatusTransitionError(self.status, PostStatus.PENDING)
        self.status = PostStatus.PENDING
        self.error_message = ""

    def is_publishable(self) -> bool:
        """True only when PENDING + content has body."""
        return (
            self.status == PostStatus.PENDING
            and self.content is not None
            and self.content.has_body()
        )
