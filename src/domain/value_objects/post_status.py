"""PostStatus — 9-state Enum for blog post lifecycle."""
from enum import Enum


class PostStatus(Enum):
    WAITING = "대기"
    GENERATING = "생성중"
    PENDING = "발행대기"
    PUBLISHING = "발행중"
    PUBLISHED = "발행완료"
    FAILED = "발행실패"
    HOLD = "보류"
    REVISION_PENDING = "수정대기"
    REVISING = "수정중"

    @classmethod
    def from_string(cls, value: str) -> "PostStatus":
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"Unknown status: {value}")
