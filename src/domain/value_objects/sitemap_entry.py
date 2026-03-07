"""SitemapEntry — Value Object for sitemap URL entries."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SitemapEntry:
    """Sitemap URL 엔트리."""

    url: str
    lastmod: str = ""
    changefreq: str = "weekly"
    priority: float = 0.8
