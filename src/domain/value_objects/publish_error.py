"""PublishError — Value Object for classified publishing errors."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PublishErrorType(Enum):
    """발행 실패 에러 유형."""
    QUOTA_EXCEEDED = "quota_exceeded"
    NETWORK_TIMEOUT = "network_timeout"
    AUTH_FAILURE = "auth_failure"
    API_ERROR = "api_error"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


class RecoveryAction(Enum):
    """에러 유형별 복구 액션."""
    AUTO_RESET = "auto_reset"          # 발행대기로 자동 전환
    AUTO_RETRY = "auto_retry"          # RetryPolicy로 재시도
    MANUAL = "manual"                  # 수동 개입 필요
    RETRY_THEN_MANUAL = "retry_then_manual"  # 1회 재시도 후 수동
    MARK_REVISION = "mark_revision"    # 수정대기로 전환


@dataclass(frozen=True)
class PublishError:
    """발행 에러 분류 결과. Immutable VO."""
    error_type: PublishErrorType
    recoverable: bool
    action: RecoveryAction
    original_message: str = ""

    @property
    def should_auto_recover(self) -> bool:
        """자동 복구 가능 여부."""
        return self.action in (RecoveryAction.AUTO_RESET, RecoveryAction.AUTO_RETRY)
