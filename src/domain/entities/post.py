"""Post — Aggregate Root entity with state machine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.domain.exceptions import InvalidStatusTransitionError
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus

MIN_CONTENT_LENGTH = 3000


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
    cwv_lcp: float | None = None
    cwv_cls: float | None = None
    revision_count: int = 0
    revised_at: datetime | None = None

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

    def reset_failed_to_revision_pending(self) -> None:
        """Retry recovery for revisions: FAILED → REVISION_PENDING."""
        if self.status != PostStatus.FAILED:
            raise InvalidStatusTransitionError(self.status, PostStatus.REVISION_PENDING)
        self.status = PostStatus.REVISION_PENDING
        self.error_message = ""

    def was_previously_published(self) -> bool:
        """True if this post has been published before (has entry_id and URL)."""
        return bool(self.entry_id) and bool(self.published_url)

    def mark_hold(self, reason: str = "") -> None:
        """PENDING → HOLD. 중복 키워드 등 발행 보류 처리."""
        if self.status != PostStatus.PENDING:
            raise InvalidStatusTransitionError(self.status, PostStatus.HOLD)
        self.status = PostStatus.HOLD
        if reason:
            self.error_message = reason[:200]

    def release_hold(self) -> None:
        """HOLD → PENDING. 관리자가 보류 사유를 확인하고 발행 후보로 되돌릴 때."""
        if self.status != PostStatus.HOLD:
            raise InvalidStatusTransitionError(self.status, PostStatus.PENDING)
        self.status = PostStatus.PENDING
        self.error_message = ""

    def reset_for_regeneration(self) -> None:
        """PENDING·HOLD·FAILED → WAITING. 대시보드 '다시 생성' — n8n이 같은 키워드로 다시 쓴다.

        발행된 적 있는 글은 거부한다. 새 글로 다시 발행되면 중복 글이 생긴다.
        """
        allowed = (PostStatus.PENDING, PostStatus.HOLD, PostStatus.FAILED)
        if self.status not in allowed or self.published_url or self.entry_id:
            raise InvalidStatusTransitionError(self.status, PostStatus.WAITING)
        self.status = PostStatus.WAITING
        self.error_message = ""

    def publish_tags(self, max_tags: int = 5) -> list[str]:
        """발행에 쓸 태그. n8n이 tags를 빠뜨리면 태그 없이 발행되던 문제 때문에,
        시트 태그가 비면 키워드 + 내부 링크 키워드로 대신한다(시트 태그는 그대로)."""
        if self.content is None:
            return []
        sheet_tags = self.content.tag_list()
        if sheet_tags:
            return sheet_tags
        seen: set[str] = set()
        tags: list[str] = []
        for raw in [self.keyword, *self.content.internal_keyword_list()]:
            tag = (raw or "").strip()
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                tags.append(tag)
        return tags[:max_tags]

    def is_publishable(self) -> bool:
        """True only when PENDING + quality body + sufficient length + quality_score."""
        return (
            self.status == PostStatus.PENDING
            and self.content is not None
            and self.content.has_body()
            and len(self.content.body_markdown or "") >= MIN_CONTENT_LENGTH
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
