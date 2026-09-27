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

# ponytail: 문장 끝(. ? !) 뒤 공백으로 자른다 — 태그 속성 안의 ". "는 잘못 자를 수 있음.
# 숫자 뒤 마침표('1.', 'Q1.')에서는 자르지 않는다 — 번호만 윗줄에 남는다
_SENTENCE_END = re.compile(r"(?<=[.?!])(?<!\d\.)\s+")
# 문장 바로 아래 붙은 목록 줄 — 빈 줄이 없으면 마크다운이 목록이 아니라 문단으로 합친다
_LIST_ITEM = r"[ \t]*(?:\d+\.|[-*+])\s"
_LIST_AFTER_TEXT = re.compile(rf"^(?!{_LIST_ITEM})(.*\S.*)\n(?={_LIST_ITEM})", re.M)
_H2_LINE = re.compile(r"^##\s+(.+?)\s*$")
_CENTER = '<p style="text-align:center">'
_BLANK_LINE = "<p><br/></p>"


def build_naver_html(markdown: str) -> str:
    """마크다운 → SmartEditor 붙여넣기용 HTML (네이버 모바일 양식).

    - 소제목(H2)은 인용구 박스, 문단은 한 문장 = 한 줄 가운데 정렬, 문단 사이 빈 줄
      (2026-09-24 실측: 셋 다 에디터 서식으로 유지된다)
    - 목차는 뺀다: 앵커 링크(#id)가 에디터에서 죽은 링크가 되고, 제목 id도 보존되지 않는다.
    """
    if not markdown or not markdown.strip():
        return ""
    markdown = _LIST_AFTER_TEXT.sub(r"\1\n\n", markdown)
    soup = BeautifulSoup(convert_markdown_to_html(markdown), "html.parser")
    for toc in soup.select(".toc-container"):
        toc.decompose()
    for anchor in soup.select('a[href^="#"]'):
        anchor.unwrap()
    for heading in soup.find_all("h2"):
        heading.replace_with(BeautifulSoup(
            f"<blockquote><p>{heading.decode_contents()}</p></blockquote>", "html.parser",
        ))
    for paragraph in soup.find_all("p"):
        if paragraph.find_parent(["li", "td", "th", "blockquote"]):
            continue
        sentences = [s for s in _SENTENCE_END.split(paragraph.decode_contents().strip()) if s]
        lines = "".join(f"{_CENTER}{s}</p>" for s in sentences)
        paragraph.replace_with(BeautifulSoup(lines + _BLANK_LINE, "html.parser"))
    for text in soup.find_all(string=True, recursive=False):
        if not text.strip():
            text.extract()
    return str(soup).strip()


def layout_blocks(markdown: str, max_images: int) -> list[tuple[str, str]]:
    """붙여넣는 순서: 대표 사진 → 도입부 → (소제목 → 사진 → 본문)…

    ('image', 소제목) / ('text', 마크다운). 발행과 미리보기가 같은 순서를 쓰게 한 곳에 둔다.
    """
    blocks: list[tuple[str, str]] = []
    images_left = max_images
    for heading, body in split_sections(markdown):
        if heading:
            blocks.append(("text", f"## {heading}"))
        if images_left:
            blocks.append(("image", heading))
            images_left -= 1
        if body:
            blocks.append(("text", body))
    return blocks


def split_sections(markdown: str) -> list[tuple[str, str]]:
    """본문을 (소제목, 그 아래 마크다운) 목록으로 나눈다. 도입부는 소제목이 빈 문자열.

    사진을 소제목 아래에 넣으려고 구간마다 따로 붙여넣는다.
    """
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in markdown.splitlines():
        match = _H2_LINE.match(line)
        if match:
            sections.append((match.group(1), []))
        else:
            sections[-1][1].append(line)
    result = [(heading, "\n".join(lines).strip()) for heading, lines in sections]
    return [s for s in result if s[0] or s[1]]


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


def parse_blog_id(url: str) -> str:
    """blog.naver.com/<블로그아이디> 형태의 URL에서 블로그 아이디를 뽑는다.

    네이버 로그인 아이디와 블로그 주소는 다를 수 있어, 로그인 후 MyBlog.naver 가 이동한
    주소로 실제 블로그 아이디를 확인한다.
    """
    parsed = urlparse(url)
    if parsed.netloc not in ("blog.naver.com", "m.blog.naver.com"):
        return ""
    first = parsed.path.strip("/").split("/")[0]
    return "" if "." in first else first


def post_url(blog_id: str, log_no: str) -> str:
    return f"{BLOG_HOST}/{blog_id}/{log_no}"
