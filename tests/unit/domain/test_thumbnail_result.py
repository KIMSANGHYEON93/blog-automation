"""Tests for ThumbnailResult value object."""
from src.domain.value_objects.thumbnail_result import ThumbnailResult


class TestThumbnailResult:
    def test_ok_result(self):
        r = ThumbnailResult.ok("http://img.url", row_index=5, keyword="Docker")
        assert r.success
        assert r.image_url == "http://img.url"
        assert r.row_index == 5
        assert r.keyword == "Docker"
        assert r.error == ""

    def test_fail_result(self):
        r = ThumbnailResult.fail("timeout", row_index=3, keyword="K8s")
        assert not r.success
        assert r.error == "timeout"
        assert r.image_url == ""
        assert r.row_index == 3

    def test_frozen(self):
        import pytest

        r = ThumbnailResult.ok("http://img.url")
        with pytest.raises(AttributeError):
            r.success = False  # type: ignore[misc]
