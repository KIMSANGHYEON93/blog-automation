"""Unit tests for markdown → HTML conversion and validation."""
from src.infrastructure.browser.tistory_editor import (
    _add_lazy_loading,
    _add_nofollow_to_external_links,
    _extract_post_id,
    _style_mermaid_fallback,
    _verify_faq_schema,
    _verify_published_url,
    convert_markdown_to_html,
    validate_html,
)


def _long_text(min_chars: int = 1600) -> str:
    """validate_html 본문 길이 검증(1,500자)을 통과할 수 있는 충분한 텍스트 생성."""
    unit = "이것은 블로그 본문 테스트 텍스트입니다. 충분한 길이를 확보하기 위해 반복합니다. "
    repeats = (min_chars // len(unit)) + 1
    return unit * repeats


def _valid_html(extra: str = "") -> str:
    """validate_html을 통과하는 기본 HTML 생성 (1,500자 이상)."""
    body = _long_text()
    return f"<h2>제목</h2><p>{body}</p>{extra}"


class TestConvertMarkdownToHtml:
    """convert_markdown_to_html() 함수 검증."""

    def test_헤딩_변환(self):
        md = "## 소개\n\n내용입니다."
        html = convert_markdown_to_html(md)
        assert "<h2" in html
        assert "소개</h2>" in html

    def test_h1_h3_변환(self):
        md = "# 큰제목\n\n### 작은제목\n\n본문"
        html = convert_markdown_to_html(md)
        # toc 확장이 id 속성을 추가하므로 부분 매칭
        assert "<h1" in html
        assert "큰제목</h1>" in html
        assert "<h3" in html
        assert "작은제목</h3>" in html

    def test_단락_변환(self):
        md = "첫 번째 단락입니다.\n\n두 번째 단락입니다."
        html = convert_markdown_to_html(md)
        assert "<p>" in html
        assert "첫 번째 단락입니다." in html

    def test_볼드_이탤릭_변환(self):
        md = "이것은 **볼드**이고 *이탤릭*입니다."
        html = convert_markdown_to_html(md)
        assert "<strong>볼드</strong>" in html
        assert "<em>이탤릭</em>" in html

    def test_테이블_변환(self):
        md = "| 항목 | 값 |\n|---|---|\n| A | 1 |\n| B | 2 |"
        html = convert_markdown_to_html(md)
        assert "<table>" in html
        assert "<th>항목</th>" in html
        assert "<td>A</td>" in html
        assert "<td>2</td>" in html

    def test_펜스_코드블록_변환(self):
        md = "```python\nprint('hello')\n```"
        html = convert_markdown_to_html(md)
        # codehilite가 활성화되어 있으므로 <div class="highlight"> 포함
        assert "print" in html

    def test_순서_목록_변환(self):
        md = "1. 첫째\n2. 둘째\n3. 셋째"
        html = convert_markdown_to_html(md)
        assert "<ol>" in html
        assert "<li>첫째</li>" in html

    def test_비순서_목록_변환(self):
        md = "- 항목 A\n- 항목 B\n- 항목 C"
        html = convert_markdown_to_html(md)
        assert "<ul>" in html
        assert "<li>항목 A</li>" in html

    def test_줄바꿈_nl2br(self):
        md = "줄 하나\n줄 둘"
        html = convert_markdown_to_html(md)
        assert "<br" in html

    def test_빈_문자열_처리(self):
        assert convert_markdown_to_html("") == ""
        assert convert_markdown_to_html("   ") == ""
        assert convert_markdown_to_html(None) == ""  # type: ignore[arg-type]

    def test_복합_콘텐츠(self):
        """실제 블로그 포스트 형태의 복합 마크다운 변환."""
        md = """## 개요

이 글에서는 **AWS**와 **Azure**를 비교합니다.

## 비교 표

| 항목 | AWS | Azure |
|---|---|---|
| 컴퓨팅 | EC2 | VM |
| 스토리지 | S3 | Blob |

### 코드 예시

```bash
aws s3 ls
```

## FAQ

1. AWS가 더 좋은가요?
2. Azure 무료 사용 가능한가요?

- 장점 1
- 장점 2
"""
        html = convert_markdown_to_html(md)
        assert "<h2" in html
        assert "개요</h2>" in html
        assert "<strong>AWS</strong>" in html
        assert "<table>" in html
        assert "<th>AWS</th>" in html
        assert "<ol>" in html
        assert "<ul>" in html


class TestConvertMarkdownToHtmlEnhanced:
    """Phase 5.7: codehilite + TOC 확장 검증."""

    def test_코드_하이라이트_인라인_스타일(self):
        """codehilite noclasses=True → inline style 속성 포함 확인."""
        md = '```python\nprint("hello")\n```'
        html = convert_markdown_to_html(md)
        # noclasses=True 이므로 style= 속성이 포함되어야 함
        assert "style=" in html

    def test_TOC_생성(self):
        """H2 2개 이상 → toc-container div 생성 확인."""
        md = "## 첫 번째 섹션\n\n내용 1\n\n## 두 번째 섹션\n\n내용 2\n\n## 세 번째 섹션\n\n내용 3"
        html = convert_markdown_to_html(md)
        assert 'class="toc-container"' in html
        assert "<h2>목차</h2>" in html

    def test_TOC_H2_앞_배치(self):
        """목차가 첫 번째 <h2> 앞에 위치하는지 확인."""
        md = "## 섹션 A\n\n내용 A\n\n## 섹션 B\n\n내용 B"
        html = convert_markdown_to_html(md)
        toc_pos = html.find('class="toc-container"')
        # 목차를 담는 div의 h2 이후, 첫 번째 콘텐츠 h2 찾기
        first_content_h2 = html.find("섹션 A</h2>")
        assert toc_pos != -1, "TOC가 생성되지 않음"
        assert first_content_h2 != -1, "첫 번째 H2가 없음"
        assert toc_pos < first_content_h2, "TOC가 첫 번째 H2 앞에 있어야 함"

    def test_이미지_lazy_loading_첫번째_제외(self):
        """_add_lazy_loading() → 첫 번째 이미지는 LCP candidate로 제외, 두 번째부터 lazy."""
        html = '<img src="first.jpg" alt="first"><p>중간</p><img src="second.jpg" alt="second">'
        result = _add_lazy_loading(html)
        # 첫 번째 이미지: lazy loading 없음 (LCP candidate)
        assert '<img src="first.jpg"' in result
        # 두 번째 이미지: lazy loading 적용
        assert '<img loading="lazy" src="second.jpg"' in result

    def test_이미지_lazy_loading_단일_이미지(self):
        """단일 이미지는 LCP candidate로 lazy loading 미적용."""
        html = '<p>텍스트</p><img src="test.jpg" alt="test"><p>끝</p>'
        result = _add_lazy_loading(html)
        assert 'loading="lazy"' not in result

    def test_lazy_loading_이미_있으면_중복_추가_안함(self):
        """이미 loading= 속성이 있는 img에는 추가하지 않음."""
        html = '<img loading="eager" src="test.jpg">'
        result = _add_lazy_loading(html)
        assert result.count("loading=") == 1

    def test_lazy_loading_빈_문자열(self):
        """빈 문자열 입력 처리."""
        assert _add_lazy_loading("") == ""
        assert _add_lazy_loading(None) is None  # type: ignore[arg-type]


class TestValidateHtml:
    """validate_html() 함수 검증."""

    def test_정상_HTML_통과(self):
        html = _valid_html()
        assert validate_html(html) is True

    def test_h3_태그도_통과(self):
        body = _long_text()
        html = f"<h3>소제목</h3><p>{body}</p>"
        assert validate_html(html) is True

    def test_빈_콘텐츠_실패(self):
        assert validate_html("") is False
        assert validate_html(None) is False  # type: ignore[arg-type]

    def test_헤딩_없으면_실패(self):
        html = "<p>본문만 있습니다.</p>"
        assert validate_html(html) is False

    def test_단락_없으면_실패(self):
        html = "<h2>제목만</h2><div>내용</div>"
        assert validate_html(html) is False

    def test_마크다운_헤딩_잔여_실패(self):
        html = "<p>## 이것은 변환되지 않은 헤딩</p>"
        assert validate_html(html) is False

    def test_마크다운_볼드_잔여_실패(self):
        html = "<h2>제목</h2><p>**변환안된볼드**</p>"
        assert validate_html(html) is False

    def test_마크다운_테이블_구분선_잔여_실패(self):
        html = "<h2>제목</h2><p>|---|---|</p>"
        assert validate_html(html) is False

    def test_코드블록_내_마크다운_문법은_무시(self):
        """<pre>/<code> 내부의 마크다운 문법은 검증에서 제외."""
        body = _long_text()
        html = (
            f'<h2>코드 예시</h2>'
            f'<p>{body}</p>'
            f'<pre><code>## 이것은 주석\n**볼드아님**\n|---|</code></pre>'
        )
        assert validate_html(html) is True

    def test_convert_후_validate_통과(self):
        """convert_markdown_to_html 결과가 validate_html을 통과하는지."""
        long_body = _long_text()
        md = f"## 제목\n\n{long_body}\n\n### 소제목\n\n추가 내용."
        html = convert_markdown_to_html(md)
        assert validate_html(html) is True


class TestValidateHtmlEnhanced:
    """Phase 5.7: validate_html() 강화 검증."""

    def test_본문_길이_부족_실패(self):
        """태그 제거 후 순수 텍스트 1,500자 미만이면 실패."""
        html = "<h2>제목</h2><p>짧은 본문입니다.</p>"
        assert validate_html(html) is False

    def test_본문_길이_충분_통과(self):
        """태그 제거 후 순수 텍스트 1,500자 이상이면 통과."""
        html = _valid_html()
        assert validate_html(html) is True

    def test_IMAGE_마커_잔류_실패(self):
        """<!-- IMAGE: keyword --> 마커가 남아있으면 hard fail."""
        body = _long_text()
        html = f"<h2>제목</h2><p>{body}</p><!-- IMAGE: server rack -->"
        assert validate_html(html) is False

    def test_이미지_없어도_경고만_통과(self):
        """<img> 태그가 0개여도 ok 플래그는 변경되지 않음 (warning only)."""
        html = _valid_html()
        assert "<img" not in html  # img 태그 없음 확인
        assert validate_html(html) is True  # 그래도 통과


class TestAddNofollowToExternalLinks:
    """_add_nofollow_to_external_links() 함수 검증."""

    def test_외부_링크에_nofollow_추가(self):
        html = '<a href="https://example.com">외부</a>'
        result = _add_nofollow_to_external_links(html, "myblog")
        assert 'rel="nofollow noopener"' in result
        assert 'target="_blank"' in result

    def test_내부_링크는_건드리지_않음(self):
        html = '<a href="https://myblog.tistory.com/123">내부</a>'
        result = _add_nofollow_to_external_links(html, "myblog")
        assert "nofollow" not in result

    def test_앵커_링크는_건드리지_않음(self):
        html = '<a href="#section1">앵커</a>'
        result = _add_nofollow_to_external_links(html, "myblog")
        assert "nofollow" not in result

    def test_이미_rel_있으면_건드리지_않음(self):
        html = '<a href="https://example.com" rel="sponsored">외부</a>'
        result = _add_nofollow_to_external_links(html, "myblog")
        assert 'rel="sponsored"' in result
        assert "nofollow" not in result

    def test_빈_문자열_처리(self):
        assert _add_nofollow_to_external_links("", "myblog") == ""


class TestMermaidFallback:
    """Mermaid 코드블록 처리 검증."""

    def test_mermaid_code_block_converted(self):
        """_preserve_mermaid_blocks가 ```mermaid를 mermaid-fallback div로 변환."""
        md = "## 제목\n\n```mermaid\ngraph TD\n    A-->B\n```"
        html = convert_markdown_to_html(md)
        assert "language-mermaid" in html
        assert "mermaid-fallback" in html

    def test_style_mermaid_fallback_wraps_div(self):
        """_style_mermaid_fallback()이 wrapper div를 추가하는지 확인."""
        html = '<pre><code class="language-mermaid">graph TD\n    A-->B</code></pre>'
        result = _style_mermaid_fallback(html)
        assert 'class="mermaid-fallback"' in result
        assert "background:#f0f4f8" in result
        assert "</code></pre></div>" in result

    def test_style_mermaid_fallback_no_mermaid_passthrough(self):
        """Mermaid 없으면 원본 그대로 반환."""
        html = "<pre><code>print('hello')</code></pre>"
        result = _style_mermaid_fallback(html)
        assert result == html


class TestValidateHtmlMermaid:
    """Mermaid 관련 validate_html() 검증."""

    def test_mermaid_residue_warning_only(self):
        """Mermaid 잔류 시 validate_html() 반환값 True (경고만)."""
        body = _long_text()
        html = (
            f'<h2>제목</h2><p>{body}</p>'
            f'<pre><code class="language-mermaid">graph TD</code></pre>'
        )
        assert validate_html(html) is True

    def test_image_marker_still_fails(self):
        """IMAGE 마커 잔류 시 여전히 False 반환."""
        body = _long_text()
        html = f"<h2>제목</h2><p>{body}</p><!-- IMAGE: server rack -->"
        assert validate_html(html) is False


class TestExtractPostId:
    """_extract_post_id() 함수 검증."""

    def test_정상_URL(self):
        assert _extract_post_id("https://blog.tistory.com/211") == "211"

    def test_경로_없음(self):
        assert _extract_post_id("https://blog.tistory.com") is None

    def test_숫자_아닌_경로(self):
        assert _extract_post_id("https://blog.tistory.com/manage") is None

    def test_빈_문자열(self):
        assert _extract_post_id("") is None


class TestVerifyPublishedUrl:
    """_verify_published_url() 함수 검증."""

    def test_200_응답(self):
        """HTTP 200 → 200 반환."""
        import http.server
        import threading

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_HEAD(self):
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass  # suppress log

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()
        try:
            code = _verify_published_url(f"http://127.0.0.1:{port}/test")
            assert code == 200
        finally:
            server.server_close()

    def test_네트워크_오류(self):
        """접속 불가 → 0 반환."""
        code = _verify_published_url("http://127.0.0.1:1/unreachable", timeout=1)
        assert code == 0


class TestVerifyFaqSchema:
    """_verify_faq_schema() 함수 검증."""

    def _serve_html(self, html_content: str) -> tuple:
        """로컬 HTTP 서버에서 HTML 응답을 제공. (server, port) 반환."""
        import http.server
        import threading

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html_content.encode("utf-8"))

            def log_message(self, *args):
                pass  # suppress log

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()
        return server, port

    def test_FAQ_스키마_존재_확인(self):
        """LD+JSON + FAQPage 포함 HTML → True."""
        html = """<html><head>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"FAQPage","mainEntity":[]}
        </script>
        </head><body><p>Hello</p></body></html>"""
        server, port = self._serve_html(html)
        try:
            assert _verify_faq_schema(f"http://127.0.0.1:{port}/test") is True
        finally:
            server.server_close()

    def test_FAQ_스키마_미존재(self):
        """LD+JSON 없는 HTML → False."""
        html = "<html><body><p>No FAQ here</p></body></html>"
        server, port = self._serve_html(html)
        try:
            assert _verify_faq_schema(f"http://127.0.0.1:{port}/test") is False
        finally:
            server.server_close()

    def test_FAQ_검증_네트워크_오류(self):
        """접근 불가 URL → False (예외 없음)."""
        assert _verify_faq_schema("http://127.0.0.1:1/unreachable", timeout=1) is False

    def test_FAQ_스키마_부분_일치_방지(self):
        """application/ld+json만 있고 FAQPage 없음 → False."""
        html = """<html><head>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Article","name":"Test"}
        </script>
        </head><body><p>Hello</p></body></html>"""
        server, port = self._serve_html(html)
        try:
            assert _verify_faq_schema(f"http://127.0.0.1:{port}/test") is False
        finally:
            server.server_close()
