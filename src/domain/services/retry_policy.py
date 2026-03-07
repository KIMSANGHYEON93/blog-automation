"""RetryPolicy — 실패 포스트 재시도 정책 (Exponential Backoff)."""
from __future__ import annotations

from datetime import datetime, timedelta


class RetryPolicy:
    """Exponential Backoff 재시도 정책.

    - 기본 간격: 1시간
    - 배수: 2 (1h → 2h → 4h)
    - 최대 재시도: 3회
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_hours: int = 1,
        multiplier: int = 2,
    ):
        self._max_retries = max_retries
        self._base_hours = base_hours
        self._multiplier = multiplier

    def is_eligible(self, retry_count: int, next_retry_at: datetime | None) -> bool:
        """재시도 가능 여부 판단.

        - retry_count < max_retries
        - next_retry_at이 없거나 현재 시간 이후
        """
        if retry_count >= self._max_retries:
            return False
        return not (next_retry_at is not None and datetime.now() < next_retry_at)

    def calculate_next_retry(self, retry_count: int) -> datetime:
        """다음 재시도 시각 계산 (현재 시간 + 백오프 간격)."""
        hours = self._base_hours * (self._multiplier ** retry_count)
        return datetime.now() + timedelta(hours=hours)

    @property
    def max_retries(self) -> int:
        return self._max_retries
