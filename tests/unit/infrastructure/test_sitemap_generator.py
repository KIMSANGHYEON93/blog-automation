"""XmlSitemapAdapter 테스트."""
from __future__ import annotations

import os
import tempfile

from src.domain.value_objects.sitemap_entry import SitemapEntry
from src.infrastructure.seo.sitemap_generator import XmlSitemapAdapter


class TestXmlSitemapAdapter:
    def test_XML_생성_파일_확인(self):
        """sitemap.xml이 올바른 XML 구조로 생성됨."""
        adapter = XmlSitemapAdapter()
        entries = [
            SitemapEntry(url="https://example.com/1", lastmod="2026-03-07"),
            SitemapEntry(url="https://example.com/2", changefreq="daily", priority=1.0),
        ]

        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            path = f.name

        try:
            result = adapter.generate(entries, path)
            assert result == path
            assert os.path.exists(path)

            with open(path, encoding="UTF-8") as f:
                content = f.read()

            assert "<?xml" in content
            assert "xmlns" in content
            assert "https://example.com/1" in content
            assert "https://example.com/2" in content
            assert "<lastmod>2026-03-07</lastmod>" in content
            assert "<changefreq>weekly</changefreq>" in content
            assert "<changefreq>daily</changefreq>" in content
            assert "<priority>0.8</priority>" in content
            assert "<priority>1.0</priority>" in content
        finally:
            os.unlink(path)

    def test_빈_엔트리(self):
        """엔트리가 비어도 빈 urlset XML 생성."""
        adapter = XmlSitemapAdapter()

        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            path = f.name

        try:
            adapter.generate([], path)
            with open(path, encoding="UTF-8") as f:
                content = f.read()
            assert "<urlset" in content
            assert "<url>" not in content
        finally:
            os.unlink(path)
