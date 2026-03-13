"""QuotaManager — Domain service for daily publishing quota management."""
from __future__ import annotations

import logging

from src.domain.value_objects.publishing_quota import PublishingQuota

logger = logging.getLogger(__name__)

DEFAULT_DAILY_LIMIT = 15


class QuotaManager:
    """일일 발행 쿼터를 사전 체크하는 도메인 서비스.

    현재는 에러 발생 후에야 감지하지만, 이 서비스로 발행 전에 미리 확인 가능.
    """

    def __init__(self, daily_limit: int = DEFAULT_DAILY_LIMIT):
        self._daily_limit = daily_limit

    def check_quota(self, published_today: int) -> PublishingQuota:
        """현재 발행 건수 기반으로 쿼터 상태 반환."""
        return PublishingQuota(
            daily_limit=self._daily_limit,
            published_today=published_today,
        )

    def can_publish(self, published_today: int, count: int = 1) -> bool:
        """지정 건수 발행 가능 여부 판단."""
        quota = self.check_quota(published_today)
        if not quota.can_publish(count):
            logger.warning(
                f"쿼터 부족: 오늘 {published_today}/{self._daily_limit}건 발행, "
                f"요청 {count}건"
            )
            return False
        return True
