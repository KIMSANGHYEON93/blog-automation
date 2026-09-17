"""Unit tests for sanitize_html — 위험 요소 제거 + 블로그 레이아웃/CWV 속성 보존."""
from src.infrastructure.browser.markdown_converter import sanitize_html


class TestSanitizeHtmlRemovesDangerousContent:
    """bleach + CSS sanitizer가 실제로 동작하는지 검증."""

    def test_script_태그_제거(self):
        result = sanitize_html('<p>본문</p><script>alert("x")</script>')
        assert "<script" not in result
        assert "<p>본문</p>" in result

    def test_이벤트_핸들러_속성_제거(self):
        result = sanitize_html('<img src="a.png" alt="a" onerror="alert(1)">')
        assert "onerror" not in result
        assert 'src="a.png"' in result

    def test_javascript_링크_제거(self):
        result = sanitize_html('<a href="javascript:alert(1)">링크</a>')
        assert "javascript:" not in result


class TestSanitizeHtmlPreservesBlogMarkup:
    """마크다운 변환 결과에 실제로 쓰이는 속성/스타일이 사라지지 않아야 함."""

    def test_img_srcset_sizes_보존(self):
        html = (
            '<img src="a-1080.jpg" alt="hero" width="1080" height="720" '
            'srcset="a-400.jpg 400w, a-1080.jpg 1080w" sizes="(max-width: 600px) 400px, 1080px">'
        )
        result = sanitize_html(html)
        assert 'srcset="a-400.jpg 400w, a-1080.jpg 1080w"' in result
        assert 'sizes="(max-width: 600px) 400px, 1080px"' in result

    def test_이미지_반응형_스타일_보존(self):
        html = (
            '<img src="a.jpg" alt="a" '
            'style="max-width:100%;height:auto;border-radius:8px;margin:16px 0;">'
        )
        result = sanitize_html(html)
        for prop in ("max-width", "height", "border-radius", "margin"):
            assert prop in result, f"{prop} 스타일이 제거됨: {result}"

    def test_코드블록_배경_스타일_보존(self):
        html = (
            '<div class="highlight" style="background: #f8f8f8">'
            "<pre><code>x = 1</code></pre></div>"
        )
        result = sanitize_html(html)
        assert "background" in result
        assert "#f8f8f8" in result

    def test_코드_하이라이트_색상_보존(self):
        html = '<span style="color: #008000; font-weight: bold">def</span>'
        result = sanitize_html(html)
        assert "color: #008000" in result
        assert "font-weight: bold" in result

    def test_빈_문자열은_그대로_반환(self):
        assert sanitize_html("") == ""
