"""Post — Aggregate Root entity with state machine."""
from __future__ import annotations

from dataclasses import dataclass, field
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
    internal_link_map: dict[str, str] | None = None
    internal_link_keywords: list[str] = field(default_factory=list)
    quality_score: int = 0
    retry_count: int = 0
    next_retry_at: datetime | None = None

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
        """True only when PENDING + content has body + quality_score >= 70."""
        return (
            self.status == PostStatus.PENDING
            and self.content is not None
            and self.content.has_body()
            and self.quality_score >= 70
        )

    def mark_revision_pending(self, reason: str = "") -> None:
        """PUBLISHED → REVISION_PENDING. reason을 error_message에 저장."""
        if self.status != PostStatus.PUBLISHED:
            raise InvalidStatusTransitionError(self.status, PostStatus.REVISION_PENDING)
        self.status = PostStatus.REVISION_PENDING
        self.error_message = reason[:200] if reason else ""

    def mark_revising(self) -> None:
        """REVISION_PENDING → REVISING."""
        if self.status != PostStatus.REVISION_PENDING:
            raise InvalidStatusTransitionError(self.status, PostStatus.REVISING)
        self.status = PostStatus.REVISING

    def mark_revised(self, url: str) -> None:
        """REVISING → PUBLISHED with updated timestamp."""
        if self.status != PostStatus.REVISING:
            raise InvalidStatusTransitionError(self.status, PostStatus.PUBLISHED)
        self.status = PostStatus.PUBLISHED
        self.published_url = url
        self.published_at = datetime.now()

    def reset_revising_to_revision_pending(self) -> None:
        """Ghost recovery: REVISING → REVISION_PENDING."""
        if self.status != PostStatus.REVISING:
            return
        self.status = PostStatus.REVISION_PENDING
        self.error_message = "이전 실행 중단으로 자동 복구됨"

    def is_revisable(self) -> bool:
        """True when REVISION_PENDING + content has body + entry_id exists."""
        return (
            self.status == PostStatus.REVISION_PENDING
            and self.content is not None
            and self.content.has_body()
            and bool(self.entry_id)
        )
