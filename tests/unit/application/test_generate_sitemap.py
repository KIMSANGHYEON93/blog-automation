"""GenerateSitemapUseCase 테스트."""
from __future__ import annotations

from datetime import datetime

from src.application.use_cases.generate_sitemap import GenerateSitemapUseCase
from src.domain.entities.post import Post
from src.domain.ports.sitemap_port import SitemapPort
from src.domain.value_objects.post_status import PostStatus
from src.domain.value_objects.sitemap_entry import SitemapEntry
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


class _StubSitemap(SitemapPort):
    """테스트용 SitemapPort 스텁."""

    def __init__(self):
        self.last_entries: list[SitemapEntry] = []
        self.last_path = ""

    def generate(self, entries: list[SitemapEntry], output_path: str) -> str:
        self.last_entries = entries
        self.last_path = output_path
        return output_path


class _ErrorSitemap(SitemapPort):
    def generate(self, entries: list, output_path: str) -> str:
        raise RuntimeError("XML 생성 실패")


def _published_post(
    row: int = 2, keyword: str = "테스트", url: str = "https://example.tistory.com/1",
) -> Post:
    post = Post(row_index=row, keyword=keyword)
    post.status = PostStatus.PUBLISHED
    post.published_url = url
    post.published_at = datetime(2026, 3, 7)
    return post


class TestGenerateSitemapUseCase:
    def test_발행완료_포스트로_sitemap_생성(self):
        """발행 완료 포스트의 URL로 sitemap 엔트리 생성."""
        repo = InMemoryPostRepository([
            _published_post(row=2, url="https://example.tistory.com/1"),
            _published_post(row=3, url="https://example.tistory.com/2"),
        ])
        sitemap = _StubSitemap()
        uc = GenerateSitemapUseCase(repo, sitemap)

        result = uc.execute("output/sitemap.xml")

        assert result.success is True
        assert result.entry_count == 2
        assert result.output_path == "output/sitemap.xml"
        assert len(sitemap.last_entries) == 2
        assert sitemap.last_entries[0].url == "https://example.tistory.com/1"
        assert sitemap.last_entries[0].lastmod == "2026-03-07"

    def test_발행_포스트_없으면_빈_결과(self):
        """발행 포스트가 없으면 entry_count=0."""
        repo = InMemoryPostRepository([])
        sitemap = _StubSitemap()
        uc = GenerateSitemapUseCase(repo, sitemap)

        result = uc.execute()

        assert result.success is True
        assert result.entry_count == 0

    def test_URL_없는_포스트_제외(self):
        """published_url이 빈 포스트는 sitemap에서 제외."""
        post_no_url = Post(row_index=4, keyword="없음")
        post_no_url.status = PostStatus.PUBLISHED
        repo = InMemoryPostRepository([
            _published_post(row=2),
            post_no_url,
        ])
        sitemap = _StubSitemap()
        uc = GenerateSitemapUseCase(repo, sitemap)

        result = uc.execute()

        assert result.entry_count == 1

    def test_생성_실패시_에러(self):
        """sitemap 생성 실패 시 error 반환."""
        repo = InMemoryPostRepository([_published_post()])
        sitemap = _ErrorSitemap()
        uc = GenerateSitemapUseCase(repo, sitemap)

        result = uc.execute()

        assert result.success is False
        assert "XML 생성 실패" in result.error
