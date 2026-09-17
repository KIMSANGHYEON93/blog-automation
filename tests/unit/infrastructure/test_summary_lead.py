"""Unit tests for insert_summary_lead — Tistory 자동 meta description이 요약문이 되도록 배치."""
import re

from src.infrastructure.browser.html_transformer import insert_summary_lead

SUMMARY = "마이크로서비스 요청 흐름을 추적하는 OpenTelemetry 구축 가이드입니다."
LEAD = f'<p class="post-summary">{SUMMARY}</p>'


def _text_before(html: str, marker: str) -> str:
    """marker 이전에 나오는 텍스트(태그 제거)."""
    return re.sub(r"<[^>]+>", "", html[: html.index(marker)]).strip()


class TestInsertSummaryLead:
    def test_목차보다_앞에_요약_삽입(self):
        html = (
            '<div class="toc-container"><h2>목차</h2><ul><li>A</li></ul></div>'
            "<h2>A</h2><p>본문</p>"
        )
        result = insert_summary_lead(html, SUMMARY)
        assert result.index(LEAD) < result.index("toc-container")

    def test_기존_도입문단보다_앞에_삽입(self):
        html = "<p>도입 문단입니다.</p><h2>A</h2>"
        result = insert_summary_lead(html, SUMMARY)
        assert result.startswith(LEAD)

    def test_히어로_이미지_뒤에_삽입(self):
        html = (
            '<figure style="max-width:100%"><img src="hero.jpg" alt="hero"></figure>'
            '<div class="toc-container"><h2>목차</h2></div>'
        )
        result = insert_summary_lead(html, SUMMARY)
        assert result.index("</figure>") < result.index(LEAD) < result.index("toc-container")
        assert _text_before(result, LEAD) == ""

    def test_이미지만_있는_문단_뒤에_삽입(self):
        html = '<p><img src="hero.jpg" alt="hero"></p><p>도입</p>'
        result = insert_summary_lead(html, SUMMARY)
        assert result.index('src="hero.jpg"') < result.index(LEAD) < result.index("<p>도입</p>")

    def test_본문_H1_제목_바로_뒤에_삽입(self):
        html = '<h1 id="title">제목</h1><div class="toc-container"><h2>목차</h2></div>'
        result = insert_summary_lead(html, SUMMARY)
        assert result.index("</h1>") < result.index(LEAD) < result.index("toc-container")
        assert _text_before(result, LEAD) == "제목"

    def test_요약_HTML_이스케이프(self):
        result = insert_summary_lead("<h2>A</h2>", 'A <script>x</script> & "B"')
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert "&amp;" in result

    def test_요약_공백_정리(self):
        result = insert_summary_lead("<h2>A</h2>", "  첫 줄\n 둘째 줄  ")
        assert '<p class="post-summary">첫 줄 둘째 줄</p>' in result

    def test_빈_요약이면_변경_없음(self):
        html = "<h2>A</h2><p>본문</p>"
        assert insert_summary_lead(html, "") == html
        assert insert_summary_lead(html, "   ") == html

    def test_이미_요약이_있으면_중복_삽입_안함(self):
        once = insert_summary_lead("<h2>A</h2>", SUMMARY)
        assert insert_summary_lead(once, SUMMARY) == once

    def test_빈_본문이면_변경_없음(self):
        assert insert_summary_lead("", SUMMARY) == ""
