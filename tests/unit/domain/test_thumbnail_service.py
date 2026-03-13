"""ThumbnailService domain service tests.

Migrated from tests/unit/infrastructure/test_thumbnail_extraction.py.
"""
from src.domain.services.thumbnail_service import ThumbnailService


class TestThumbnailService:
    """HTML 본문에서 대표이미지 URL 추출 테스트."""

    def test_basic_img_extraction(self):
        html = '<p>Hello</p><img src="https://example.com/photo.jpg">'
        assert ThumbnailService.extract_first_image_url(html) == "https://example.com/photo.jpg"

    def test_returns_first_of_multiple_images(self):
        html = (
            '<img src="https://first.com/a.png">'
            '<img src="https://second.com/b.png">'
        )
        assert ThumbnailService.extract_first_image_url(html) == "https://first.com/a.png"

    def test_skips_data_uri(self):
        html = (
            '<img src="data:image/png;base64,abc123">'
            '<img src="https://real.com/img.jpg">'
        )
        assert ThumbnailService.extract_first_image_url(html) == "https://real.com/img.jpg"

    def test_skips_relative_path(self):
        html = (
            '<img src="/images/local.png">'
            '<img src="https://cdn.example.com/pic.webp">'
        )
        assert ThumbnailService.extract_first_image_url(html) == "https://cdn.example.com/pic.webp"

    def test_no_images_returns_empty(self):
        html = "<p>No images here</p><div>Just text</div>"
        assert ThumbnailService.extract_first_image_url(html) == ""

    def test_empty_html_returns_empty(self):
        assert ThumbnailService.extract_first_image_url("") == ""

    def test_only_data_uris_returns_empty(self):
        html = (
            '<img src="data:image/gif;base64,R0lGODlh">'
            '<img src="data:image/png;base64,iVBOR">'
        )
        assert ThumbnailService.extract_first_image_url(html) == ""

    def test_single_quoted_src(self):
        html = "<img src='https://example.com/single.jpg'>"
        assert ThumbnailService.extract_first_image_url(html) == "https://example.com/single.jpg"

    def test_src_with_preceding_attributes(self):
        html = '<img class="thumb" alt="photo" src="https://example.com/attr.jpg">'
        assert ThumbnailService.extract_first_image_url(html) == "https://example.com/attr.jpg"
