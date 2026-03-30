"""inline_styler — 발행 HTML에 인라인 스타일 주입 (Tistory 외부 CSS 불가 대응).

BeautifulSoup 기반 순수 함수 모듈 — 외부 상태 없음.
기존 style 속성이 있으면 보존하고 뒤에 추가한다.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------

_TABLE_STYLE = (
    "width:100%;border-collapse:collapse;margin:24px 0;"
    "font-size:15px;line-height:1.6"
)
_TH_STYLE = (
    "background:#f8f9fa;border:1px solid #dee2e6;"
    "padding:12px 16px;text-align:left;font-weight:600"
)
_TD_STYLE = "border:1px solid #dee2e6;padding:10px 16px"
_TD_EVEN_BG = "background:#f8f9fa"
_TABLE_WRAPPER_STYLE = "overflow-x:auto;-webkit-overflow-scrolling:touch"

_TH_PROS_BG = "background:#d4edda;color:#155724"
_TH_CONS_BG = "background:#f8d7da;color:#721c24"
_TD_PROS_BG = "background:#d4edda"
_TD_CONS_BG = "background:#f8d7da"

_PROS_PATTERN = re.compile(r"장점")
_CONS_PATTERN = re.compile(r"단점|한계")

_TOC_WRAPPER_STYLE = (
    "background:#f8f9fa;border:1px solid #e9ecef;"
    "border-left:4px solid #4a90d9;border-radius:8px;"
    "padding:20px 24px;margin:24px 0"
)
_TOC_HEADING_STYLE = "margin-top:0;margin-bottom:12px;font-size:18px"
_TOC_LINK_STYLE = "color:#4a90d9;text-decoration:none"

_H2_STYLE = (
    "font-size:24px;font-weight:700;color:#1a1a2e;"
    "margin:40px 0 16px;padding-bottom:8px;border-bottom:2px solid #4a90d9"
)
_H3_STYLE = (
    "font-size:20px;font-weight:600;color:#2d2d44;"
    "margin:32px 0 12px;padding-left:12px;border-left:3px solid #4a90d9"
)

_HIGHLIGHT_DIV_STYLE = (
    "background:#282c34;border-radius:8px;margin:20px 0;overflow-x:auto"
)
_HIGHLIGHT_PRE_STYLE = "padding:16px 20px;margin:0;font-size:14px;line-height:1.5"
_INLINE_CODE_STYLE = (
    "background:#f0f4f8;padding:2px 6px;border-radius:4px;"
    "font-size:0.9em;color:#e83e8c"
)

_BLOCKQUOTE_STYLE = (
    "margin:24px 0;padding:16px 20px;background:#f0f4f8;"
    "border-left:4px solid #4a90d9;border-radius:0 8px 8px 0"
)
_LIST_STYLE = "margin:16px 0;padding-left:24px;line-height:1.8"

_PARAGRAPH_STYLE = "margin:16px 0;line-height:1.8;color:#333;word-break:keep-all"
_TD_HEADER_STYLE = (
    "background:#f8f9fa;border:1px solid #dee2e6;"
    "padding:12px 16px;text-align:left;font-weight:600"
)

_LINK_STYLE = "color:#4a90d9;text-decoration:none"
_HR_STYLE = "border:none;border-top:1px solid #e9ecef;margin:32px 0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_style(tag: Tag, new_style: str) -> None:
    """기존 style 속성 보존 + 뒤에 새 스타일 추가."""
    existing = str(tag.get("style", "")).strip()
    merged = existing.rstrip(";") + ";" + new_style if existing else new_style
    tag["style"] = merged


def _is_toc_container(tag: Tag) -> bool:
    """toc-container 클래스를 가진 요소인지 확인."""
    classes = tag.get("class", [])
    return "toc-container" in classes


def _inside_toc(tag: Tag) -> bool:
    """태그가 toc-container 내부에 있는지 확인."""
    return any(isinstance(parent, Tag) and _is_toc_container(parent) for parent in tag.parents)


def _inside_pre(tag: Tag) -> bool:
    """태그가 <pre> 내부에 있는지 확인."""
    return any(isinstance(parent, Tag) and parent.name == "pre" for parent in tag.parents)


def _detect_column_type(th_tag: Tag) -> str | None:
    """<th> 텍스트로 장점/단점 컬럼 타입 감지.

    Returns: 'pros', 'cons', or None
    """
    text = th_tag.get_text(strip=True)
    if _PROS_PATTERN.search(text):
        return "pros"
    if _CONS_PATTERN.search(text):
        return "cons"
    return None


# ---------------------------------------------------------------------------
# Step 1: Table styles + responsive wrapper
# ---------------------------------------------------------------------------

def _style_tables(soup: BeautifulSoup) -> None:
    for table in soup.find_all("table"):
        _merge_style(table, _TABLE_STYLE)

        # 장단점 컬럼 인덱스 감지
        col_types: dict[int, str] = {}
        for row in table.find_all("tr"):
            ths = row.find_all("th")
            for idx, th in enumerate(ths):
                col_type = _detect_column_type(th)
                if col_type:
                    col_types[idx] = col_type

        # <th> 스타일
        has_th = bool(table.find("th"))
        for th in table.find_all("th"):
            col_type = _detect_column_type(th)
            if col_type == "pros":
                _merge_style(th, _TH_STYLE + ";" + _TH_PROS_BG)
            elif col_type == "cons":
                _merge_style(th, _TH_STYLE + ";" + _TH_CONS_BG)
            else:
                _merge_style(th, _TH_STYLE)

        # <td> 스타일 + 짝수행 배경 + 장단점 배경
        all_rows = table.find_all("tr")
        data_row_idx = 0
        first_row_as_header = not has_th and len(all_rows) > 1
        for row_idx, row in enumerate(all_rows):
            tds = row.find_all("td")
            if not tds:
                continue
            # <th> 없는 테이블: 첫 번째 행을 헤더로 스타일링
            if first_row_as_header and row_idx == 0:
                for td in tds:
                    _merge_style(td, _TD_HEADER_STYLE)
                continue
            data_row_idx += 1
            is_even = data_row_idx % 2 == 0
            for td_idx, td in enumerate(tds):
                base = _TD_STYLE
                if td_idx in col_types:
                    ct = col_types[td_idx]
                    bg = _TD_PROS_BG if ct == "pros" else _TD_CONS_BG
                    _merge_style(td, base + ";" + bg)
                elif is_even:
                    _merge_style(td, base + ";" + _TD_EVEN_BG)
                else:
                    _merge_style(td, base)

        # Responsive wrapper
        wrapper = soup.new_tag("div")
        wrapper["style"] = _TABLE_WRAPPER_STYLE
        table.wrap(wrapper)


# ---------------------------------------------------------------------------
# Step 2: TOC styles
# ---------------------------------------------------------------------------

def _style_toc(soup: BeautifulSoup) -> None:
    for toc in soup.find_all("div", class_="toc-container"):
        _merge_style(toc, _TOC_WRAPPER_STYLE)
        h2 = toc.find("h2")
        if h2 and h2.get_text(strip=True) == "목차":
            _merge_style(h2, _TOC_HEADING_STYLE)
        for a in toc.find_all("a"):
            _merge_style(a, _TOC_LINK_STYLE)


# ---------------------------------------------------------------------------
# Step 3: Heading styles (H2, H3) — exclude TOC headings
# ---------------------------------------------------------------------------

def _style_headings(soup: BeautifulSoup) -> None:
    for h2 in soup.find_all("h2"):
        if _inside_toc(h2):
            continue
        _merge_style(h2, _H2_STYLE)

    for h3 in soup.find_all("h3"):
        if _inside_toc(h3):
            continue
        _merge_style(h3, _H3_STYLE)


# ---------------------------------------------------------------------------
# Step 4: Code block container styles
# ---------------------------------------------------------------------------

def _style_code_blocks(soup: BeautifulSoup) -> None:
    # <div class="highlight"> container
    for div in soup.find_all("div", class_="highlight"):
        _merge_style(div, _HIGHLIGHT_DIV_STYLE)
        pre = div.find("pre")
        if pre:
            _merge_style(pre, _HIGHLIGHT_PRE_STYLE)

    # Inline <code> outside <pre>
    for code in soup.find_all("code"):
        if _inside_pre(code):
            continue
        _merge_style(code, _INLINE_CODE_STYLE)


# ---------------------------------------------------------------------------
# Step 5: Blockquote + list styles
# ---------------------------------------------------------------------------

def _style_blockquotes_and_lists(soup: BeautifulSoup) -> None:
    for bq in soup.find_all("blockquote"):
        _merge_style(bq, _BLOCKQUOTE_STYLE)

    for tag in soup.find_all(["ul", "ol"]):
        # TOC 내부 리스트는 제외
        if _inside_toc(tag):
            continue
        _merge_style(tag, _LIST_STYLE)


# ---------------------------------------------------------------------------
# Step 6: Link + horizontal rule styles
# ---------------------------------------------------------------------------

def _style_links_and_hr(soup: BeautifulSoup) -> None:
    for a in soup.find_all("a"):
        # TOC 내부 링크는 Step 2에서 처리됨
        if _inside_toc(a):
            continue
        _merge_style(a, _LINK_STYLE)

    for hr in soup.find_all("hr"):
        _merge_style(hr, _HR_STYLE)


# ---------------------------------------------------------------------------
# Step 7: Paragraph styles
# ---------------------------------------------------------------------------

def _inside_table(tag: Tag) -> bool:
    """태그가 <table> 내부에 있는지 확인."""
    return any(isinstance(p, Tag) and p.name == "table" for p in tag.parents)


def _style_paragraphs(soup: BeautifulSoup) -> None:
    for p in soup.find_all("p"):
        # TOC / blockquote / table 내부 단락은 제외
        if _inside_toc(p) or _inside_table(p):
            continue
        if any(
            isinstance(parent, Tag) and parent.name == "blockquote"
            for parent in p.parents
        ):
            continue
        _merge_style(p, _PARAGRAPH_STYLE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_inline_styles(html: str) -> str:
    """발행 HTML에 인라인 스타일을 주입.

    적용 순서:
    1. 테이블 스타일 + 반응형 wrapper
    2. TOC 스타일
    3. 헤딩 (H2, H3) 스타일
    4. 코드블록 컨테이너 스타일
    5. 인용구 + 리스트 스타일
    6. 링크 + 수평선 스타일
    7. 단락 스타일
    """
    if not html or not html.strip():
        return html

    soup = BeautifulSoup(html, "html.parser")

    _style_tables(soup)
    _style_toc(soup)
    _style_headings(soup)
    _style_code_blocks(soup)
    _style_blockquotes_and_lists(soup)
    _style_links_and_hr(soup)
    _style_paragraphs(soup)

    return str(soup)
