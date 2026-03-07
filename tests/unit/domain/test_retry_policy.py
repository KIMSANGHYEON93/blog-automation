"""RetryPolicy 테스트."""
from __future__ import annotations

from datetime import datetime, timedelta

from src.domain.services.retry_policy import RetryPolicy


class TestRetryPolicy:
    def test_첫_재시도_가능(self):
        """retry_count=0 → 재시도 가능."""
        policy = RetryPolicy()
        assert policy.is_eligible(retry_count=0, next_retry_at=None) is True

    def test_최대_재시도_초과_불가(self):
        """retry_count >= max_retries → 재시도 불가."""
        policy = RetryPolicy(max_retries=3)
        assert policy.is_eligible(retry_count=3, next_retry_at=None) is False
        assert policy.is_eligible(retry_count=5, next_retry_at=None) is False

    def test_다음_재시도_시간_전_불가(self):
        """next_retry_at이 미래 → 재시도 불가."""
        policy = RetryPolicy()
        future = datetime.now() + timedelta(hours=2)
        assert policy.is_eligible(retry_count=1, next_retry_at=future) is False

    def test_다음_재시도_시간_후_가능(self):
        """next_retry_at이 과거 → 재시도 가능."""
        policy = RetryPolicy()
        past = datetime.now() - timedelta(hours=1)
        assert policy.is_eligible(retry_count=1, next_retry_at=past) is True

    def test_백오프_간격_계산(self):
        """1h → 2h → 4h exponential backoff."""
        policy = RetryPolicy(base_hours=1, multiplier=2)

        # retry_count=0: 1 × 2^0 = 1시간
        t0 = policy.calculate_next_retry(0)
        expected_0 = datetime.now() + timedelta(hours=1)
        assert abs((t0 - expected_0).total_seconds()) < 2

        # retry_count=1: 1 × 2^1 = 2시간
        t1 = policy.calculate_next_retry(1)
        expected_1 = datetime.now() + timedelta(hours=2)
        assert abs((t1 - expected_1).total_seconds()) < 2

        # retry_count=2: 1 × 2^2 = 4시간
        t2 = policy.calculate_next_retry(2)
        expected_2 = datetime.now() + timedelta(hours=4)
        assert abs((t2 - expected_2).total_seconds()) < 2

    def test_max_retries_프로퍼티(self):
        policy = RetryPolicy(max_retries=5)
        assert policy.max_retries == 5
