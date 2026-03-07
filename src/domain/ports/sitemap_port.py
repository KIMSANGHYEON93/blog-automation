"""SitemapPort — Domain interface for sitemap generation."""
from __future__ import annotations

from abc import ABC, abstractmethod


class SitemapPort(ABC):
    @abstractmethod
    def generate(self, entries: list, output_path: str) -> str:
        """sitemap XML 생성 → 파일 경로 반환."""
        ...
