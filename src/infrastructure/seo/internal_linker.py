"""내부 링크 자동 삽입 모듈.

본문 HTML에서 키워드 첫 출현 위치를 내부 링크로 교체한다.
- 한 글에 최대 5개 내부 링크 제한
- <h1>~<h3>, <a>, <code>, <pre> 내부는 변환 제외
"""
from __future__ import annotations

import re

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
        keywords: 현재 포스트의 internal_link_keywords 리스트
        published_posts: 발행 완료된 Post 객체 리스트 (keyword, published_url 사용)

    Returns:
        내부 링크가 삽입된 HTML
    """
    if not html or not published_posts:
        return html

    # 키워드 → URL 매핑 (published_posts 기반)
    keyword_url_map: dict[str, str] = {}
    for post in published_posts:
        if post.keyword and post.published_url:
            keyword_url_map[post.keyword.strip().lower()] = post.published_url

    if not keyword_url_map:
        return html

    # 매칭할 키워드 결정: internal_link_keywords가 있으면 그 중에서,
    # 없으면 published_posts의 키워드를 직접 사용
    target_keywords: list[str] = []
    if keywords:
        for kw in keywords:
            if kw.lower() in keyword_url_map:
                target_keywords.append(kw)
    else:
        target_keywords = [
            post.keyword for post in published_posts
            if post.keyword and post.published_url
        ]

    if not target_keywords:
        return html

    # 교체 가능한 텍스트 구간 식별
    replaceable_ranges = _find_replaceable_ranges(html)
    if not replaceable_ranges:
        return html

    # 키워드별 첫 출현 위치 찾기 + 링크 교체 (최대 _MAX_LINKS개)
    replacements: list[tuple[int, int, str, str]] = []
    used_keywords: set[str] = set()

    for kw in target_keywords:
        if len(replacements) >= _MAX_LINKS:
            break
        kw_lower = kw.lower()
        if kw_lower in used_keywords:
            continue

        url = keyword_url_map.get(kw_lower)
        if not url:
            continue

        # 대소문자 무시 매칭
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
