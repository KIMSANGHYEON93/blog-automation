"""Domain exception hierarchy."""


class DomainError(Exception):
    """Base exception for all domain errors."""


class InvalidStatusTransition(DomainError):
    """Raised when a post status transition violates business rules."""

    def __init__(self, current_status, target_status):
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(
            f"Cannot transition from {current_status.value} to {target_status.value}"
        )


class PostNotPublishable(DomainError):
    """Raised when attempting to publish a post that is not in publishable state."""


class ContentMissing(DomainError):
    """Raised when post content is required but missing."""
