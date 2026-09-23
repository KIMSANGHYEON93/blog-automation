"""네이버 블로그 발행용 순수 변환 함수 — 브라우저 없이 테스트 가능.

네이버는 쓰기 API가 2020년에 종료돼 SmartEditor ONE에 HTML을 붙여넣는 방식만 남았다.
본문 HTML은 티스토리와 같은 변환기를 쓰되, 에디터가 처리하지 못하는 요소만 뺀다.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from src.infrastructure.browser.markdown_converter import convert_markdown_to_html

# 네이버 블로그 글 하나에 붙일 수 있는 태그 수 상한
MAX_TAGS = 30

BLOG_HOST = "https://blog.naver.com"

_LOG_NO_PATH = re.compile(r"^/[^/]+/(\d{6,})/?$")


def build_naver_html(markdown: str) -> str:
    """마크다운 → SmartEditor 붙여넣기용 HTML.

    목차는 뺀다: 앵커 링크(#id)가 에디터에서 죽은 링크가 되고, 제목 id도 보존되지 않는다.
    """
    if not markdown or not markdown.strip():
        return ""
    soup = BeautifulSoup(convert_markdown_to_html(markdown), "html.parser")
    for toc in soup.select(".toc-container"):
        toc.decompose()
    for anchor in soup.select('a[href^="#"]'):
        anchor.unwrap()
    return str(soup).strip()


def normalize_tags(tags: list[str]) -> list[str]:
    """'#'·공백 제거, 중복·빈 값 제거, 상한 적용. 입력 순서 유지."""
    seen: list[str] = []
    for raw in tags:
        tag = raw.strip().lstrip("#").strip()
        if tag and tag not in seen:
            seen.append(tag)
    return seen[:MAX_TAGS]


def parse_log_no(url: str) -> str:
    """발행 후 URL에서 글 번호(logNo)를 뽑는다. 없으면 빈 문자열."""
    if not url:
        return ""
    parsed = urlparse(url)
    query_log_no = parse_qs(parsed.query).get("logNo")
    if query_log_no:
        return query_log_no[0]
    match = _LOG_NO_PATH.match(parsed.path)
    return match.group(1) if match else ""


def post_url(blog_id: str, log_no: str) -> str:
    return f"{BLOG_HOST}/{blog_id}/{log_no}"
