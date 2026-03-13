"""HtmlValidationService domain service tests."""
from src.domain.services.html_validation import HtmlValidationService


def _make_valid_html(length: int = 2000) -> str:
    """최소 검증 통과하는 HTML 생성."""
    body = "테스트 콘텐츠 " * (length // 7 + 1)
    return (
        f'<h2>제목</h2><p>{body}</p>'
        f'<img src="https://example.com/img.jpg">'
    )


class TestHtmlValidationService:
    def setup_method(self):
        self.svc = HtmlValidationService()

    def test_valid_html_passes(self):
        html = _make_valid_html()
        result = self.svc.validate(html)
        assert result.passed is True
        assert len(result.errors) == 0

    def test_empty_html_fails(self):
        result = self.svc.validate("")
        assert result.passed is False
        assert "빈 콘텐츠" in result.errors[0]

    def test_missing_heading_fails(self):
        html = "<p>" + "콘텐츠 " * 300 + "</p>"
        result = self.svc.validate(html)
        assert result.passed is False
        assert any("<h2>/<h3>" in e for e in result.errors)

    def test_missing_paragraph_fails(self):
        html = "<h2>제목</h2><div>" + "콘텐츠 " * 300 + "</div>"
        result = self.svc.validate(html)
        assert result.passed is False
        assert any("<p>" in e for e in result.errors)

    def test_residual_markdown_heading_fails(self):
        body = "콘텐츠 " * 300
        html = f"<h2>제목</h2><p>{body}</p>\n## 잔여 마크다운"
        result = self.svc.validate(html)
        assert result.passed is False
        assert any("마크다운 헤딩" in e for e in result.errors)

    def test_residual_bold_markdown_fails(self):
        body = "콘텐츠 " * 300
        html = f"<h2>제목</h2><p>{body} **볼드텍스트** 추가</p>"
        result = self.svc.validate(html)
        assert result.passed is False
        assert any("볼드" in e for e in result.errors)

    def test_short_content_fails(self):
        html = "<h2>제목</h2><p>짧은 본문</p>"
        result = self.svc.validate(html)
        assert result.passed is False
        assert any("본문 길이 부족" in e for e in result.errors)

    def test_image_marker_residual_fails(self):
        html = _make_valid_html() + "<!-- IMAGE: photo.jpg -->"
        result = self.svc.validate(html)
        assert result.passed is False
        assert any("IMAGE 마커" in e for e in result.errors)

    def test_no_images_warning_only(self):
        body = "콘텐츠 " * 300
        html = f"<h2>제목</h2><p>{body}</p>"
        result = self.svc.validate(html)
        # img 없어도 passed=True (warning only)
        assert any("<img>" in w for w in result.warnings)

    def test_mermaid_residual_warning(self):
        html = _make_valid_html() + '<pre><code class="language-mermaid">graph TD</code></pre>'
        result = self.svc.validate(html)
        assert any("Mermaid" in w for w in result.warnings)

    def test_is_valid_shortcut(self):
        assert self.svc.is_valid(_make_valid_html()) is True
        assert self.svc.is_valid("") is False

    def test_markdown_in_code_block_ignored(self):
        """코드 블록 내 마크다운 문법은 무시."""
        body = "콘텐츠입니다 " * 400
        html = (
            f'<h2>제목</h2><p>{body}</p>'
            '<pre><code>## 이것은 코드 블록</code></pre>'
            '<img src="https://example.com/img.jpg">'
        )
        result = self.svc.validate(html)
        assert result.passed is True
