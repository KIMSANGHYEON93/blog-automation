"""PublishResult value object tests — TDD RED phase."""
import pytest

from src.domain.value_objects.publish_result import PublishResult


class TestPublishResult:
    def test_ok_factory(self):
        r = PublishResult.ok("https://blog.tistory.com/123")
        assert r.success is True
        assert r.url == "https://blog.tistory.com/123"
        assert r.error == ""

    def test_fail_factory(self):
        r = PublishResult.fail("셀렉터 찾기 실패")
        assert r.success is False
        assert r.url == ""
        assert r.error == "셀렉터 찾기 실패"

    def test_ok_has_url(self):
        r = PublishResult.ok("https://example.com")
        assert r.url != ""

    def test_fail_has_error(self):
        r = PublishResult.fail("에러 메시지")
        assert r.error != ""

    def test_is_immutable(self):
        r = PublishResult.ok("https://test.com")
        with pytest.raises(AttributeError):
            r.success = False
