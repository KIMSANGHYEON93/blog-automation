"""Domain exception hierarchy."""


class DomainError(Exception):
    """Base exception for all domain errors."""


class InvalidStatusTransitionError(DomainError):
    """Raised when a post status transition violates business rules."""

    def __init__(self, current_status, target_status):
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(
            f"Cannot transition from {current_status.value} to {target_status.value}"
        )


class PostNotPublishableError(DomainError):
    """Raised when attempting to publish a post that is not in publishable state."""


class ContentMissingError(DomainError):
    """Raised when post content is required but missing."""


class DailyPublishLimitError(DomainError):
    """Raised when the blog platform's daily publish limit is reached."""


class PostNotRevisableError(DomainError):
    """수정 불가 상태에서 수정 시도 시 발생."""


class LoginFailedError(DomainError):
    """블로그 플랫폼 로그인 실패.

    조용히 return하면 exit 0이 되어 launchd가 성공으로 기록하고,
    장애가 몇 달간 드러나지 않는다(2026-05-06 ~ 09-21 실제 사례).
    예외로 올려 main()의 알림·non-zero 종료 경로를 타게 한다.
    """
