"""네이버 블로그 발행용 순수 변환 함수 테스트 (브라우저 불필요)."""
from src.infrastructure.browser.naver.content import (
    MAX_TAGS,
    build_naver_html,
    normalize_tags,
    parse_log_no,
    post_url,
)


class TestBuildNaverHtml:
    def test_converts_markdown_headings_and_paragraphs(self):
        html = build_naver_html("## 소제목\n\n본문 문단")
        assert "<h2" in html
        assert "본문 문단" in html

    def test_drops_toc_because_anchor_links_break_in_smart_editor(self):
        md = "## 첫째\n\n가\n\n## 둘째\n\n나"
        html = build_naver_html(md)
        assert "toc-container" not in html
        assert 'href="#' not in html

    def test_empty_markdown_returns_empty(self):
        assert build_naver_html("") == ""
        assert build_naver_html("   ") == ""


class TestNormalizeTags:
    def test_strips_hash_and_whitespace(self):
        assert normalize_tags(["#API ", " 쿠버네티스"]) == ["API", "쿠버네티스"]

    def test_removes_duplicates_and_empty(self):
        assert normalize_tags(["a", "", "a", "#", "b"]) == ["a", "b"]

    def test_limits_to_naver_maximum(self):
        tags = [f"t{i}" for i in range(MAX_TAGS + 5)]
        assert len(normalize_tags(tags)) == MAX_TAGS


class TestParseLogNo:
    def test_pretty_url(self):
        assert parse_log_no("https://blog.naver.com/myblog/223456789012") == "223456789012"

    def test_postview_query_url(self):
        url = "https://blog.naver.com/PostView.naver?blogId=myblog&logNo=223456789012&x=1"
        assert parse_log_no(url) == "223456789012"

    def test_mobile_url(self):
        assert parse_log_no("https://m.blog.naver.com/myblog/223456789012") == "223456789012"

    def test_editor_url_has_no_log_no(self):
        assert parse_log_no("https://blog.naver.com/myblog/postwrite") == ""
        assert parse_log_no("") == ""


def test_post_url():
    assert post_url("myblog", "123") == "https://blog.naver.com/myblog/123"
