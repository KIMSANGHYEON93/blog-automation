"""네이버 블로그 발행용 순수 변환 함수 테스트 (브라우저 불필요)."""
from src.infrastructure.browser.naver.content import (
    MAX_TAGS,
    build_naver_html,
    normalize_tags,
    parse_blog_id,
    parse_log_no,
    post_url,
)


class TestBuildNaverHtml:
    def test_소제목은_인용구_박스로(self):
        html = build_naver_html("## 소제목\n\n본문 문단")
        assert "<h2" not in html
        assert "<blockquote><p>소제목</p></blockquote>" in html

    def test_문장마다_가운데_정렬_한_줄_문단_사이_빈_줄(self):
        html = build_naver_html("첫 문장이에요. 둘째 문장인가요? 셋째!\n\n다음 문단이에요.")
        center = '<p style="text-align:center">'
        assert f"{center}첫 문장이에요.</p>{center}둘째 문장인가요?</p>{center}셋째!</p>" in html
        assert f"셋째!</p><p><br/></p>{center}다음 문단이에요.</p>" in html

    def test_목록_안의_문장은_그대로(self):
        html = build_naver_html("- 가. 나.\n- 다")
        assert "text-align:center" not in html

    def test_문장_안_굵게는_유지(self):
        html = build_naver_html("이건 **중요**해요. 끝이에요.")
        assert "<strong>중요</strong>해요.</p>" in html

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


class TestParseBlogId:
    # 로그인 아이디와 블로그 주소가 다를 수 있다(kuk6475 → sangpedia, 2026-09-23 실측)
    def test_blog_home_url(self):
        assert parse_blog_id("https://blog.naver.com/sangpedia") == "sangpedia"

    def test_ignores_query(self):
        assert parse_blog_id("https://blog.naver.com/sangpedia?Redirect=Write") == "sangpedia"

    def test_login_page_is_not_a_blog(self):
        assert parse_blog_id("https://nid.naver.com/nidlogin.login") == ""


def test_post_url():
    assert post_url("myblog", "123") == "https://blog.naver.com/myblog/123"


class TestSplitSections:
    def test_도입부와_소제목별로_나눈다(self):
        from src.infrastructure.browser.naver.content import split_sections

        md = "도입 문장.\n\n## 첫째\n\n가 문단.\n\n## 둘째\n\n나 문단."
        assert split_sections(md) == [
            ("", "도입 문장."),
            ("첫째", "가 문단."),
            ("둘째", "나 문단."),
        ]

    def test_도입부가_없으면_빈_도입부를_만들지_않는다(self):
        from src.infrastructure.browser.naver.content import split_sections

        assert split_sections("## 첫째\n\n가.") == [("첫째", "가.")]


class TestNumberedSteps:
    def test_문장_바로_아래_번호_목록도_목록으로(self):
        # 2026-09-24 실측: 빈 줄 없이 붙은 '1.'이 문단으로 합쳐져 번호만 윗줄에 남았다
        html = build_naver_html("설명이에요.\n1. 첫째 단계예요.\n2. 둘째 단계예요.")
        assert "<ol>" in html
        assert "첫째 단계예요.</li>" in html
        assert "1.</p>" not in html

    def test_번호_뒤에서는_문장을_자르지_않는다(self):
        html = build_naver_html("Q1. 요금은 얼마인가요? 버전 3.5 기준이에요.")
        assert '<p style="text-align:center">Q1. 요금은 얼마인가요?</p>' in html
