"""PublishingQuota — Value Object for daily publishing quota tracking."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PublishingQuota:
    """일일 발행 쿼터 상태."""

    daily_limit: int
    published_today: int

    @property
    def remaining(self) -> int:
        """남은 발행 가능 건수."""
        return max(0, self.daily_limit - self.published_today)

    @property
    def is_exhausted(self) -> bool:
        """쿼터 소진 여부."""
        return self.remaining <= 0

    def can_publish(self, count: int = 1) -> bool:
        """지정 건수 발행 가능 여부."""
        return self.remaining >= count
