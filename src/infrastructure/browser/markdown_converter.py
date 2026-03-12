"""markdown_converter — Markdown to HTML conversion with Mermaid support."""
from __future__ import annotations

import logging
import re

import markdown as md_lib

logger = logging.getLogger(__name__)


def _render_mermaid_via_kroki(code: str) -> str | None:
    """kroki.io API로 Mermaid 코드를 SVG로 렌더링.

    POST https://kroki.io/mermaid/svg 에 plaintext body를 전송하여 SVG를 반환받는다.
    실패 시 None을 반환한다 (graceful degradation).
    """
    import urllib.request

    try:
        req = urllib.request.Request(
            "https://kroki.io/mermaid/svg",
            data=code.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            svg = resp.read().decode("utf-8")
        if "<svg" in svg:
            return svg
        return None
    except Exception:
        return None


def _preserve_mermaid_blocks(md_text: str) -> str:
    """잔류 Mermaid 코드블록을 SVG 또는 styled HTML로 사전 변환.

    1차: kroki.io API로 SVG 렌더링 시도
    2차 (실패 시): styled fallback <div>로 변환
    codehilite extension이 ```mermaid 블록을 구문 강조 처리하여
    language-mermaid 클래스가 사라지는 것을 방지한다.
    Markdown은 raw HTML을 그대로 통과시키므로, 사전에 HTML로 변환한다.
    """
    import html as html_lib

    def _replace(match: re.Match) -> str:
        code = match.group(1).strip()
        first_line = code.split("\n")[0].strip()
        alt_text = f"Mermaid diagram: {first_line}"
        safe_alt = alt_text.replace('"', "&quot;")

        # 1차: kroki.io SVG 렌더링 시도
        svg = _render_mermaid_via_kroki(code)
        if svg:
            # SVG에 width가 없으면 반응형 설정
            processed_svg = svg
            if "width=" not in processed_svg:
                processed_svg = processed_svg.replace("<svg", '<svg width="100%"', 1)
            return (
                f'<div class="mermaid-diagram" role="img" aria-label="{safe_alt}" '
                f'style="max-width:100%;overflow-x:auto;margin:16px 0;">'
                f"{processed_svg}</div>"
            )

        # 2차: fallback — styled code block
        escaped_code = html_lib.escape(code)
        return (
            '<div class="mermaid-fallback" style="background:#f0f4f8;border:1px solid #d0d7de;'
            'border-radius:6px;padding:8px;margin:16px 0;overflow-x:auto;">'
            f'<pre><code class="language-mermaid">{escaped_code}</code></pre></div>'
        )

    # 1) [MERMAID]...[/MERMAID] 커스텀 마커 (Pipeline A에서 inject_images.js 실패 시 잔류)
    result = re.sub(r"\[MERMAID\]([\s\S]*?)\[/MERMAID\]", _replace, md_text)
    # 2) ```mermaid...``` 코드블록 (하위호환)
    return re.sub(r"```mermaid\n([\s\S]*?)```", _replace, result)


def convert_markdown_to_html(md_text: str) -> str:
    """마크다운 텍스트를 HTML로 변환.

    Extensions: tables, fenced_code, nl2br, sane_lists, codehilite, toc
    - codehilite: noclasses=True → 인라인 스타일 (외부 CSS 불필요)
    - toc: H2~H3 목차 자동 생성, 첫 번째 <h2> 앞에 삽입
    - 잔류 Mermaid 블록: codehilite 처리 전에 styled HTML로 사전 변환
    """
    if not md_text or not md_text.strip():
        return ""

    # Mermaid 코드블록 사전 처리 (codehilite보다 먼저 실행)
    md_text = _preserve_mermaid_blocks(md_text)

    extensions = ["tables", "fenced_code", "nl2br", "sane_lists", "codehilite", "toc"]
    extension_configs = {
        "codehilite": {"css_class": "highlight", "linenums": False, "noclasses": True},
        "toc": {"permalink": False, "toc_depth": "2-3"},
    }
    md = md_lib.Markdown(extensions=extensions, extension_configs=extension_configs)
    html_body: str = md.convert(md_text)

    # TOC 자동 삽입: 첫 번째 <h2> 앞에 목차 배치
    toc_html = getattr(md, "toc", "")
    if toc_html and "<li>" in toc_html:
        toc_block = f'<div class="toc-container"><h2>목차</h2>{toc_html}</div>\n\n'
        h2_pos = html_body.find("<h2")
        if h2_pos >= 0:
            html_body = html_body[:h2_pos] + toc_block + html_body[h2_pos:]

    # Mermaid fallback 스타일링 (렌더링 실패한 잔류 코드블록에 시각적 힌트)
    html_body = style_mermaid_fallback(html_body)

    return html_body


def style_mermaid_fallback(html_text: str) -> str:
    """렌더링 실패한 Mermaid 코드블록에 시각적 힌트 추가.

    <pre><code class="language-mermaid">...  →
    <div class="mermaid-fallback" style="..."><pre><code>...
    """
    if 'language-mermaid' not in html_text:
        return html_text

    return re.sub(
        r'(<pre[^>]*><code[^>]*class="[^"]*language-mermaid[^"]*"[^>]*>)',
        r'<div class="mermaid-fallback" style="background:#f0f4f8;border:1px solid #d0d7de;'
        r'border-radius:6px;padding:8px;margin:16px 0;overflow-x:auto;">\1',
        html_text,
    ).replace('</code></pre>', '</code></pre></div>')
