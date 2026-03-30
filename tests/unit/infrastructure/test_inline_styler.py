"""inline_styler 단위 테스트 — 인라인 스타일 주입 검증."""
from __future__ import annotations

from bs4 import BeautifulSoup

from src.infrastructure.seo.inline_styler import apply_inline_styles


def _parse(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_string(self):
        assert apply_inline_styles("") == ""

    def test_whitespace_only(self):
        assert apply_inline_styles("   ") == "   "

    def test_none_like_falsy(self):
        # 빈 문자열 외 falsy 값은 그대로 반환
        result = apply_inline_styles("")
        assert result == ""

    def test_preserves_existing_style(self):
        html = '<h2 style="color:red">Title</h2>'
        result = apply_inline_styles(html)
        soup = _parse(result)
        style = soup.find("h2")["style"]
        assert "color:red" in style
        assert "font-size:24px" in style


# ---------------------------------------------------------------------------
# Step 1: Table styles
# ---------------------------------------------------------------------------

class TestTableStyles:
    def test_table_gets_style(self):
        html = "<table><tr><th>A</th></tr><tr><td>1</td></tr></table>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        table = soup.find("table")
        assert "border-collapse:collapse" in table["style"]
        assert "width:100%" in table["style"]

    def test_th_gets_style(self):
        html = "<table><tr><th>Header</th></tr></table>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        th = soup.find("th")
        assert "font-weight:600" in th["style"]
        assert "background:#f8f9fa" in th["style"]

    def test_td_gets_style(self):
        html = "<table><tr><td>Cell</td></tr></table>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        td = soup.find("td")
        assert "padding:10px 16px" in td["style"]

    def test_even_row_background(self):
        html = (
            "<table>"
            "<tr><th>Header</th></tr>"
            "<tr><td>Row1</td></tr>"
            "<tr><td>Row2</td></tr>"
            "<tr><td>Row3</td></tr>"
            "</table>"
        )
        result = apply_inline_styles(html)
        soup = _parse(result)
        tds = soup.find_all("td")
        # Row 1 (odd): no background
        assert "background:#f8f9fa" not in tds[0]["style"]
        # Row 2 (even): has background
        assert "background:#f8f9fa" in tds[1]["style"]
        # Row 3 (odd): no background
        assert "background:#f8f9fa" not in tds[2]["style"]

    def test_responsive_wrapper(self):
        html = "<table><tr><td>Cell</td></tr></table>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        wrapper = soup.find("div")
        assert wrapper is not None
        assert "overflow-x:auto" in wrapper["style"]
        # table is inside wrapper
        assert wrapper.find("table") is not None

    def test_pros_cons_detection(self):
        html = (
            "<table>"
            "<tr><th>장점</th><th>단점</th></tr>"
            "<tr><td>Fast</td><td>Expensive</td></tr>"
            "</table>"
        )
        result = apply_inline_styles(html)
        soup = _parse(result)
        ths = soup.find_all("th")
        # 장점 th
        assert "#d4edda" in ths[0]["style"]
        assert "#155724" in ths[0]["style"]
        # 단점 th
        assert "#f8d7da" in ths[1]["style"]
        assert "#721c24" in ths[1]["style"]

    def test_pros_cons_td_background(self):
        html = (
            "<table>"
            "<tr><th>장점</th><th>단점</th></tr>"
            "<tr><td>Fast</td><td>Expensive</td></tr>"
            "</table>"
        )
        result = apply_inline_styles(html)
        soup = _parse(result)
        tds = soup.find_all("td")
        assert "#d4edda" in tds[0]["style"]
        assert "#f8d7da" in tds[1]["style"]

    def test_cons_keyword_한계(self):
        html = "<table><tr><th>한계</th></tr><tr><td>Limited</td></tr></table>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        th = soup.find("th")
        assert "#f8d7da" in th["style"]

    def test_no_th_first_row_as_header(self):
        """<th> 없는 테이블: 첫 번째 행을 헤더처럼 스타일링."""
        html = (
            "<table>"
            "<tr><td>항목</td><td>설명</td></tr>"
            "<tr><td>A</td><td>Desc A</td></tr>"
            "</table>"
        )
        result = apply_inline_styles(html)
        soup = _parse(result)
        tds = soup.find_all("td")
        # 첫 행: 헤더 스타일
        assert "font-weight:600" in tds[0]["style"]
        assert "background:#f8f9fa" in tds[0]["style"]
        assert "font-weight:600" in tds[1]["style"]
        # 두 번째 행: 일반 td 스타일
        assert "font-weight:600" not in tds[2]["style"]

    def test_single_row_table_no_header_fallback(self):
        """행이 1개뿐인 테이블은 헤더 폴백 적용하지 않음."""
        html = "<table><tr><td>Only</td></tr></table>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        td = soup.find("td")
        assert "font-weight:600" not in td["style"]


# ---------------------------------------------------------------------------
# Step 2: TOC styles
# ---------------------------------------------------------------------------

class TestTocStyles:
    def test_toc_container_style(self):
        html = '<div class="toc-container"><h2>목차</h2><ul><li><a href="#s">S</a></li></ul></div>'
        result = apply_inline_styles(html)
        soup = _parse(result)
        toc = soup.find("div", class_="toc-container")
        assert "border-left:4px solid #4a90d9" in toc["style"]
        assert "border-radius:8px" in toc["style"]

    def test_toc_heading_style(self):
        html = '<div class="toc-container"><h2>목차</h2></div>'
        result = apply_inline_styles(html)
        soup = _parse(result)
        h2 = soup.find("h2")
        assert "margin-top:0" in h2["style"]
        assert "font-size:18px" in h2["style"]

    def test_toc_link_style(self):
        html = '<div class="toc-container"><a href="#x">Link</a></div>'
        result = apply_inline_styles(html)
        soup = _parse(result)
        a = soup.find("a")
        assert "color:#4a90d9" in a["style"]

    def test_toc_list_not_styled_by_general_list(self):
        """TOC 내부 리스트는 일반 리스트 스타일이 적용되지 않아야 함."""
        html = '<div class="toc-container"><ul><li>Item</li></ul></div>'
        result = apply_inline_styles(html)
        soup = _parse(result)
        ul = soup.find("ul")
        style = ul.get("style", "")
        assert "line-height:1.8" not in style


# ---------------------------------------------------------------------------
# Step 3: Heading styles
# ---------------------------------------------------------------------------

class TestHeadingStyles:
    def test_h2_style(self):
        html = "<h2>Section Title</h2>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        h2 = soup.find("h2")
        assert "font-size:24px" in h2["style"]
        assert "border-bottom:2px solid #4a90d9" in h2["style"]

    def test_h3_style(self):
        html = "<h3>Subsection</h3>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        h3 = soup.find("h3")
        assert "font-size:20px" in h3["style"]
        assert "border-left:3px solid #4a90d9" in h3["style"]

    def test_toc_h2_excluded_from_heading_style(self):
        """TOC 내부 <h2>목차</h2>는 헤딩 스타일이 아닌 TOC 스타일이 적용됨."""
        html = '<div class="toc-container"><h2>목차</h2></div><h2>Real Title</h2>'
        result = apply_inline_styles(html)
        soup = _parse(result)
        h2s = soup.find_all("h2")
        # TOC h2: TOC 스타일
        assert "margin-top:0" in h2s[0]["style"]
        assert "border-bottom:2px solid #4a90d9" not in h2s[0]["style"]
        # Normal h2: 헤딩 스타일
        assert "border-bottom:2px solid #4a90d9" in h2s[1]["style"]


# ---------------------------------------------------------------------------
# Step 4: Code block styles
# ---------------------------------------------------------------------------

class TestCodeBlockStyles:
    def test_highlight_div_style(self):
        html = '<div class="highlight"><pre><code>x = 1</code></pre></div>'
        result = apply_inline_styles(html)
        soup = _parse(result)
        div = soup.find("div", class_="highlight")
        assert "background:#282c34" in div["style"]
        assert "border-radius:8px" in div["style"]

    def test_highlight_pre_style(self):
        html = '<div class="highlight"><pre><code>x = 1</code></pre></div>'
        result = apply_inline_styles(html)
        soup = _parse(result)
        pre = soup.find("pre")
        assert "padding:16px 20px" in pre["style"]

    def test_inline_code_style(self):
        html = "<p>Use <code>pip install</code> to install.</p>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        code = soup.find("code")
        assert "background:#f0f4f8" in code["style"]
        assert "color:#e83e8c" in code["style"]

    def test_code_inside_pre_not_styled_as_inline(self):
        """<pre> 내부 <code>는 인라인 코드 스타일이 적용되지 않아야 함."""
        html = "<pre><code>block code</code></pre>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        code = soup.find("code")
        style = code.get("style", "")
        assert "color:#e83e8c" not in style


# ---------------------------------------------------------------------------
# Step 5: Blockquote + list styles
# ---------------------------------------------------------------------------

class TestBlockquoteAndListStyles:
    def test_blockquote_style(self):
        html = "<blockquote><p>Quote text</p></blockquote>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        bq = soup.find("blockquote")
        assert "border-left:4px solid #4a90d9" in bq["style"]
        assert "background:#f0f4f8" in bq["style"]

    def test_ul_style(self):
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        ul = soup.find("ul")
        assert "line-height:1.8" in ul["style"]
        assert "padding-left:24px" in ul["style"]

    def test_ol_style(self):
        html = "<ol><li>Step 1</li></ol>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        ol = soup.find("ol")
        assert "line-height:1.8" in ol["style"]


# ---------------------------------------------------------------------------
# Step 6: Link + HR styles
# ---------------------------------------------------------------------------

class TestLinkAndHrStyles:
    def test_link_style(self):
        html = '<p><a href="https://example.com">Link</a></p>'
        result = apply_inline_styles(html)
        soup = _parse(result)
        a = soup.find("a")
        assert "color:#4a90d9" in a["style"]
        assert "text-decoration:none" in a["style"]

    def test_hr_style(self):
        html = "<p>Above</p><hr><p>Below</p>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        hr = soup.find("hr")
        assert "border:none" in hr["style"]
        assert "border-top:1px solid #e9ecef" in hr["style"]

    def test_toc_link_not_doubled(self):
        """TOC 내부 링크는 일반 링크 스타일이 중복 적용되지 않아야 함."""
        html = '<div class="toc-container"><a href="#s">TOC Link</a></div>'
        result = apply_inline_styles(html)
        soup = _parse(result)
        a = soup.find("a")
        style = a["style"]
        # TOC 링크 스타일만 적용 (중복 없음)
        assert style.count("color:#4a90d9") == 1


# ---------------------------------------------------------------------------
# Step 7: Paragraph styles
# ---------------------------------------------------------------------------

class TestParagraphStyles:
    def test_paragraph_gets_style(self):
        html = "<p>Hello world</p>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        p = soup.find("p")
        assert "line-height:1.8" in p["style"]
        assert "word-break:keep-all" in p["style"]

    def test_toc_paragraph_excluded(self):
        """TOC 내부 <p>는 단락 스타일이 적용되지 않아야 함."""
        html = '<div class="toc-container"><p>TOC text</p></div>'
        result = apply_inline_styles(html)
        soup = _parse(result)
        p = soup.find("p")
        style = p.get("style", "")
        assert "line-height:1.8" not in style

    def test_blockquote_paragraph_excluded(self):
        """<blockquote> 내부 <p>는 단락 스타일이 적용되지 않아야 함."""
        html = "<blockquote><p>Quote</p></blockquote>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        p = soup.find("p")
        style = p.get("style", "")
        assert "line-height:1.8" not in style

    def test_table_paragraph_excluded(self):
        """<td> 내부 <p>는 단락 스타일이 적용되지 않아야 함."""
        html = "<table><tr><th>H</th></tr><tr><td><p>Cell text</p></td></tr></table>"
        result = apply_inline_styles(html)
        soup = _parse(result)
        p = soup.find("p")
        style = p.get("style", "")
        assert "margin:16px 0" not in style


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_complete_html(self):
        """모든 요소가 포함된 HTML에서 스타일이 올바르게 적용되는지 확인."""
        html = """
        <div class="toc-container">
            <h2>목차</h2>
            <ul><li><a href="#intro">소개</a></li></ul>
        </div>
        <h2 id="intro">소개</h2>
        <p>This is <code>inline code</code> in a paragraph.</p>
        <h3>Details</h3>
        <table>
            <tr><th>장점</th><th>단점</th></tr>
            <tr><td>Fast</td><td>Complex</td></tr>
        </table>
        <div class="highlight"><pre><code>print("hello")</code></pre></div>
        <blockquote><p>A wise quote</p></blockquote>
        <ul><li>Item A</li></ul>
        <ol><li>Step 1</li></ol>
        <a href="https://example.com">External</a>
        <hr>
        """
        result = apply_inline_styles(html)
        soup = _parse(result)

        # TOC styled
        toc = soup.find("div", class_="toc-container")
        assert "border-left:4px solid #4a90d9" in toc["style"]

        # H2 styled (not TOC h2)
        h2s = soup.find_all("h2")
        non_toc_h2 = [h for h in h2s if "border-bottom:2px solid" in h.get("style", "")]
        assert len(non_toc_h2) == 1

        # H3 styled
        h3 = soup.find("h3")
        assert "border-left:3px solid" in h3["style"]

        # Table styled with wrapper
        wrapper_divs = soup.find_all(
            "div",
            style=lambda s: s and "-webkit-overflow-scrolling:touch" in s,
        )
        assert len(wrapper_divs) == 1

        # Blockquote styled
        bq = soup.find("blockquote")
        assert "background:#f0f4f8" in bq["style"]

        # HR styled
        hr = soup.find("hr")
        assert "border:none" in hr["style"]
