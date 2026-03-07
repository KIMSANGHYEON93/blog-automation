"""SitemapEntry VO 테스트."""
import pytest

from src.domain.value_objects.sitemap_entry import SitemapEntry


class TestSitemapEntry:
    def test_기본값(self):
        entry = SitemapEntry(url="https://example.com/1")
        assert entry.url == "https://example.com/1"
        assert entry.changefreq == "weekly"
        assert entry.priority == 0.8
        assert entry.lastmod == ""

    def test_frozen(self):
        entry = SitemapEntry(url="https://example.com/1")
        with pytest.raises(AttributeError):
            entry.url = "changed"  # type: ignore[misc]

    def test_커스텀_값(self):
        entry = SitemapEntry(
            url="https://example.com/2",
            lastmod="2026-03-07",
            changefreq="daily",
            priority=1.0,
        )
        assert entry.lastmod == "2026-03-07"
        assert entry.changefreq == "daily"
        assert entry.priority == 1.0
