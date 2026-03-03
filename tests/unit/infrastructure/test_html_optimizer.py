"""HTML 최적화 모듈 테스트 — 6건."""
from __future__ import annotations

from src.infrastructure.seo.html_optimizer import optimize_html, validate_responsive


class TestOptimizeHtml:
    def test_img_lazy_loading_추가(self):
        """<img src="x"> → loading="lazy" 속성 부여."""
        html = '<html><body><img src="test.jpg"></body></html>'
        result = optimize_html(html)
        assert 'loading="lazy"' in result
        assert 'decoding="async"' in result

    def test_img_이미_lazy면_중복_안함(self):
        """기존 loading="lazy" → 변경 없음."""
        html = '<html><body><img src="test.jpg" loading="lazy"></body></html>'
        result = optimize_html(html)
        assert result.count('loading="lazy"') == 1

    def test_img_반응형_스타일_추가(self):
        """width/height 미지정 img → max-width:100% 스타일."""
        html = '<html><body><img src="test.jpg"></body></html>'
        result = optimize_html(html)
        assert "max-width:100%" in result
        assert "height:auto" in result

    def test_img_width_height_있으면_스타일_안추가(self):
        """width/height 지정 img → max-width 스타일 미추가."""
        html = '<html><body><img src="test.jpg" width="300" height="200"></body></html>'
        result = optimize_html(html)
        assert "max-width:100%" not in result

    def test_iframe_lazy_추가(self):
        """iframe에 loading="lazy" 부여."""
        html = '<html><body><iframe src="https://example.com"></iframe></body></html>'
        result = optimize_html(html)
        assert 'loading="lazy"' in result

    def test_viewport_메타_주입(self):
        """viewport 없는 HTML → 자동 주입."""
        html = "<html><head><title>Test</title></head><body></body></html>"
        result = optimize_html(html)
        assert 'name="viewport"' in result
        assert "width=device-width" in result


class TestValidateResponsive:
    def test_validate_responsive_문제_감지(self):
        """고정 width px → 경고 반환."""
        html = '<html><body><div style="width: 500px">content</div></body></html>'
        issues = validate_responsive(html)
        assert any("고정 width px" in issue for issue in issues)
        assert any("viewport" in issue for issue in issues)

    def test_validate_responsive_정상(self):
        """문제 없는 HTML → 빈 리스트."""
        html = (
            "<html><head>"
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            "</head><body>"
            '<img src="test.jpg" loading="lazy">'
            "</body></html>"
        )
        issues = validate_responsive(html)
        assert issues == []
