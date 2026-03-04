"""내부 링크 자동 삽입 모듈.

본문 HTML에서 키워드 첫 출현 위치를 내부 링크로 교체한다.
- 한 글에 최대 5개 내부 링크 제한
- <h1>~<h3>, <a>, <code>, <pre> 내부는 변환 제외

전략:
  1) internal_link_keywords → published URL 매칭 (정확/부분 문자열)
  2) published 키워드를 HTML 본문에서 직접 검색 (1번에서 빈 슬롯 보충)
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_SKIP_TAGS = frozenset({"h1", "h2", "h3", "a", "code", "pre"})
_MAX_LINKS = 5


def inject_internal_links(
    html: str,
    keywords: list[str],
    published_posts: list,
) -> str:
    """본문 HTML에 내부 링크를 삽입한다.

    Args:
        html: 원본 HTML 본문
        keywords: 현재 포스트의 internal_link_keywords 리스트 (빈 리스트 가능)
        published_posts: 발행 완료된 Post 객체 리스트 (keyword, published_url 사용)

    Returns:
        내부 링크가 삽입된 HTML
    """
    if not html or not published_posts:
        return html

    # published keyword(lower) → URL 매핑
    keyword_url_map: dict[str, str] = {}
    # published keyword(original) → URL (원본 케이스 보존)
    keyword_url_orig: dict[str, str] = {}
    for post in published_posts:
        if post.keyword and post.published_url:
            kw = post.keyword.strip()
            keyword_url_map[kw.lower()] = post.published_url
            keyword_url_orig[kw] = post.published_url

    if not keyword_url_map:
        return html

    # --- 전략 1: internal_link_keywords → URL 매칭 ---
    kw_to_url: dict[str, str] = {}
    if keywords:
        for kw in keywords:
            kw_lower = kw.lower()
            # 정확 매칭
            if kw_lower in keyword_url_map:
                kw_to_url[kw] = keyword_url_map[kw_lower]
                continue
            # 양방향 부분 문자열 매칭
            for pub_kw, url in keyword_url_map.items():
                if kw_lower in pub_kw or pub_kw in kw_lower:
                    kw_to_url[kw] = url
                    break

    matched_from_keywords = len(kw_to_url)

    # --- 전략 2: published 키워드를 직접 후보에 추가 (빈 슬롯 보충) ---
    if len(kw_to_url) < _MAX_LINKS:
        used_urls = set(kw_to_url.values())
        for orig_kw, url in keyword_url_orig.items():
            if len(kw_to_url) >= _MAX_LINKS:
                break
            if url in used_urls:
                continue
            if orig_kw not in kw_to_url:
                kw_to_url[orig_kw] = url
                used_urls.add(url)

    if not kw_to_url:
        return html

    logger.debug(
        "내부 링크 후보: keyword매칭=%d, published직접=%d, 총=%d",
        matched_from_keywords,
        len(kw_to_url) - matched_from_keywords,
        len(kw_to_url),
    )

    # 교체 가능한 텍스트 구간 식별
    replaceable_ranges = _find_replaceable_ranges(html)
    if not replaceable_ranges:
        return html

    # 키워드 길이 내림차순 정렬 (긴 키워드 우선 매칭, 부분 중복 방지)
    target_keywords = sorted(kw_to_url.keys(), key=len, reverse=True)

    # 키워드별 첫 출현 위치 찾기 + 링크 교체 (최대 _MAX_LINKS개)
    replacements: list[tuple[int, int, str, str]] = []
    used_keywords: set[str] = set()

    for kw in target_keywords:
        if len(replacements) >= _MAX_LINKS:
            break
        kw_lower = kw.lower()
        if kw_lower in used_keywords:
            continue

        url = kw_to_url.get(kw)
        if not url:
            continue

        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        for match in pattern.finditer(html):
            start, end = match.start(), match.end()
            if _is_in_replaceable_range(start, end, replaceable_ranges):
                original = match.group()
                link = f'<a href="{url}">{original}</a>'
                replacements.append((start, end, original, link))
                used_keywords.add(kw_lower)
                break

    if not replacements:
        return html

    # 역순 교체 (인덱스 유지)
    replacements.sort(key=lambda r: r[0], reverse=True)
    result = html
    for start, end, _original, link in replacements:
        result = result[:start] + link + result[end:]

    return result


def _find_replaceable_ranges(html: str) -> list[tuple[int, int]]:
    """skip 태그 외부의 텍스트 구간을 반환한다."""
    ranges: list[tuple[int, int]] = []
    skip_depth = 0
    i = 0
    text_start = -1

    while i < len(html):
        if html[i] == "<":
            # 현재 텍스트 구간 종료
            if text_start >= 0 and skip_depth == 0:
                ranges.append((text_start, i))
            text_start = -1

            # 태그 끝 찾기
            tag_end = html.find(">", i)
            if tag_end == -1:
                break

            tag_content = html[i + 1: tag_end].strip()

            # 닫는 태그
            if tag_content.startswith("/"):
                tag_name = (
                    tag_content[1:].split()[0].lower()
                    if tag_content[1:].strip()
                    else ""
                )
                if tag_name in _SKIP_TAGS and skip_depth > 0:
                    skip_depth -= 1
            else:
                # 여는 태그
                tag_name = tag_content.split()[0].split("/")[0].lower()
                if tag_name in _SKIP_TAGS:
                    skip_depth += 1

            i = tag_end + 1
        else:
            if text_start < 0:
                text_start = i
            i += 1

    # 마지막 텍스트 구간
    if text_start >= 0 and skip_depth == 0:
        ranges.append((text_start, len(html)))

    return ranges


def _is_in_replaceable_range(
    start: int, end: int, ranges: list[tuple[int, int]],
) -> bool:
    """주어진 위치가 교체 가능한 범위 안에 있는지 확인."""
    return any(
        start >= r_start and end <= r_end for r_start, r_end in ranges
    )
