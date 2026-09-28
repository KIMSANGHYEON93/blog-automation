"""네이버 발행 미리보기 — 에디터에 붙일 HTML을 사진 자리와 함께, 대시보드에서 안전하게 보이게.

발행과 같은 layout_blocks·build_naver_html을 쓰므로 미리보기와 실제 글이 어긋나지 않는다.
시트 본문은 LLM이 쓴 것이라 믿지 않는다 — 허용 태그만 남긴다.
"""
from __future__ import annotations

from html import escape

import bleach  # type: ignore[import-untyped]
from bs4 import BeautifulSoup

from src.infrastructure.browser.naver.adapter import MAX_IMAGES
from src.infrastructure.browser.naver.content import build_naver_html, layout_blocks

_TAGS = [
    "p", "br", "strong", "b", "em", "i", "u", "s", "code", "pre", "blockquote",
    "h3", "h4", "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td", "a", "hr", "div",
]
_ATTRS = {"a": ["href"], "p": ["class"], "div": ["class"]}


def build_preview_html(keyword: str, markdown: str) -> str:
    parts = []
    first_image = True
    for kind, value in layout_blocks(markdown, MAX_IMAGES):
        if kind == "image":
            if first_image:
                parts.append('<div class="photo">대표 썸네일 · 제목이 들어간 사진</div>')
            else:
                parts.append(f'<div class="photo">사진 · {escape(f"{keyword} · {value}")}</div>')
            first_image = False
        else:
            parts.append(build_naver_html(value))
    soup = BeautifulSoup("".join(parts), "html.parser")
    # 대시보드 CSP가 인라인 style을 막으므로 가운데 정렬은 클래스로 옮긴다
    for paragraph in soup.find_all("p", style=True):
        if "center" in paragraph["style"]:
            paragraph["class"] = "c"
        del paragraph["style"]
    return str(bleach.clean(
        str(soup), tags=_TAGS, attributes=_ATTRS, protocols=["http", "https"], strip=True,
    ))
