"""QuotaManager domain service tests."""
from src.domain.services.quota_manager import QuotaManager
from src.domain.value_objects.publishing_quota import PublishingQuota


class TestPublishingQuota:
    def test_remaining_calculation(self):
        q = PublishingQuota(daily_limit=15, published_today=10)
        assert q.remaining == 5

    def test_exhausted_when_at_limit(self):
        q = PublishingQuota(daily_limit=15, published_today=15)
        assert q.is_exhausted is True
        assert q.remaining == 0

    def test_not_exhausted_when_below_limit(self):
        q = PublishingQuota(daily_limit=15, published_today=5)
        assert q.is_exhausted is False

    def test_can_publish_within_quota(self):
        q = PublishingQuota(daily_limit=15, published_today=13)
        assert q.can_publish(2) is True
        assert q.can_publish(3) is False

    def test_remaining_never_negative(self):
        q = PublishingQuota(daily_limit=15, published_today=20)
        assert q.remaining == 0


class TestQuotaManager:
    def test_check_quota_returns_quota_vo(self):
        mgr = QuotaManager(daily_limit=15)
        quota = mgr.check_quota(published_today=10)
        assert isinstance(quota, PublishingQuota)
        assert quota.remaining == 5

    def test_can_publish_true(self):
        mgr = QuotaManager(daily_limit=15)
        assert mgr.can_publish(published_today=10, count=5) is True

    def test_can_publish_false_at_limit(self):
        mgr = QuotaManager(daily_limit=15)
        assert mgr.can_publish(published_today=15) is False

    def test_custom_daily_limit(self):
        mgr = QuotaManager(daily_limit=5)
        assert mgr.can_publish(published_today=4, count=2) is False
        assert mgr.can_publish(published_today=4, count=1) is True
