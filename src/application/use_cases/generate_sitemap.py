"""GenerateSitemapUseCase — 발행 완료 포스트로 sitemap.xml 생성."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.domain.ports.post_repository import PostRepository
from src.domain.ports.sitemap_port import SitemapPort
from src.domain.value_objects.sitemap_entry import SitemapEntry

logger = logging.getLogger(__name__)


@dataclass
class SitemapResult:
    """Sitemap 생성 결과 DTO."""

    success: bool
    entry_count: int = 0
    output_path: str = ""
    error: str = ""


class GenerateSitemapUseCase:
    """발행 완료 포스트의 URL로 sitemap.xml을 생성."""

    def __init__(self, repo: PostRepository, sitemap: SitemapPort):
        self._repo = repo
        self._sitemap = sitemap

    def execute(self, output_path: str = "sitemap.xml") -> SitemapResult:
        published = self._repo.find_published(limit=500)

        if not published:
            logger.info("sitemap 생성 대상 포스트 없음")
            return SitemapResult(success=True, entry_count=0)

        entries = []
        for post in published:
            if not post.published_url:
                continue
            lastmod = ""
            if post.published_at:
                lastmod = post.published_at.strftime("%Y-%m-%d")
            entries.append(SitemapEntry(
                url=post.published_url,
                lastmod=lastmod,
            ))

        if not entries:
            return SitemapResult(success=True, entry_count=0)

        try:
            path = self._sitemap.generate(entries, output_path)
            logger.info(f"sitemap.xml 생성 완료: {len(entries)}개 URL → {path}")
            return SitemapResult(
                success=True,
                entry_count=len(entries),
                output_path=path,
            )
        except Exception as e:
            logger.error(f"sitemap 생성 실패: {e}")
            return SitemapResult(success=False, error=str(e)[:200])
