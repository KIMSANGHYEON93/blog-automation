"""ErrorClassifier — Domain service for classifying publish errors."""
from __future__ import annotations

import re

from src.domain.value_objects.publish_error import (
    PublishError,
    PublishErrorType,
    RecoveryAction,
)

# 에러 메시지 패턴 → 에러 유형 매핑
_QUOTA = re.compile(r"최대 \d+개까지|quota|daily.?limit", re.IGNORECASE)
_TIMEOUT = re.compile(r"timeout|timed?\s*out|연결.?시간", re.IGNORECASE)
_AUTH = re.compile(
    r"login|로그인|auth|인증|session.?expired|세션", re.IGNORECASE,
)
_API = re.compile(r"api.?error|500|502|503|서버.?오류", re.IGNORECASE)
_VALID = re.compile(r"valid|검증|본문.?길이|HTML 검증", re.IGNORECASE)

_PATTERNS: list[tuple[re.Pattern, PublishErrorType]] = [
    (_QUOTA, PublishErrorType.QUOTA_EXCEEDED),
    (_TIMEOUT, PublishErrorType.NETWORK_TIMEOUT),
    (_AUTH, PublishErrorType.AUTH_FAILURE),
    (_API, PublishErrorType.API_ERROR),
    (_VALID, PublishErrorType.VALIDATION),
]

# 에러 유형 → (복구 가능 여부, 복구 액션) 매핑
_RECOVERY_MAP: dict[PublishErrorType, tuple[bool, RecoveryAction]] = {
    PublishErrorType.QUOTA_EXCEEDED: (True, RecoveryAction.AUTO_RESET),
    PublishErrorType.NETWORK_TIMEOUT: (True, RecoveryAction.AUTO_RETRY),
    PublishErrorType.AUTH_FAILURE: (False, RecoveryAction.MANUAL),
    PublishErrorType.API_ERROR: (True, RecoveryAction.RETRY_THEN_MANUAL),
    PublishErrorType.VALIDATION: (False, RecoveryAction.MARK_REVISION),
    PublishErrorType.UNKNOWN: (False, RecoveryAction.MANUAL),
}


class ErrorClassifier:
    """발행 에러를 유형별로 분류하고 복구 전략을 결정하는 도메인 서비스."""

    def classify(self, error_message: str) -> PublishError:
        """에러 메시지를 분석하여 PublishError VO 반환."""
        if not error_message:
            return PublishError(
                error_type=PublishErrorType.UNKNOWN,
                recoverable=False,
                action=RecoveryAction.MANUAL,
                original_message="",
            )

        error_type = self._detect_type(error_message)
        recoverable, action = _RECOVERY_MAP[error_type]

        return PublishError(
            error_type=error_type,
            recoverable=recoverable,
            action=action,
            original_message=error_message,
        )

    def _detect_type(self, message: str) -> PublishErrorType:
        """에러 메시지에서 패턴 매칭으로 에러 유형 결정."""
        for pattern, error_type in _PATTERNS:
            if pattern.search(message):
                return error_type
        return PublishErrorType.UNKNOWN
