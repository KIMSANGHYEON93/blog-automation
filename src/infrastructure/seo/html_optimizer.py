"""발행 HTML의 반응형 + 성능 최적화 모듈.

BeautifulSoup을 활용한 순수 함수 — 외부 상태 없음.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup


def optimize_html(html: str) -> str:
    """발행 HTML의 반응형 + 성능 최적화.

    적용 항목:
    - <img>: loading="lazy", decoding="async"
    - <img>: width/height 미지정 시 max-width:100% 스타일
    - <iframe>: loading="lazy"
    - 외부 리소스 <link>: rel="preconnect" 힌트 추가
    - viewport 메타 태그 미포함 시 주입
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. <img> 최적화
    for img in soup.find_all("img"):
        if not img.get("loading"):
            img["loading"] = "lazy"
        if not img.get("decoding"):
            img["decoding"] = "async"
        if not img.get("width") and not img.get("height"):
            existing_style = img.get("style", "")
            if "max-width" not in existing_style:
                new_style = "max-width:100%;height:auto"
                if existing_style:
                    new_style = existing_style.rstrip(";") + ";" + new_style
                img["style"] = new_style

    # 2. <iframe> 최적화
    for iframe in soup.find_all("iframe"):
        if not iframe.get("loading"):
            iframe["loading"] = "lazy"

    # 3. 외부 리소스 preconnect 힌트
    _add_preconnect_hints(soup)

    # 4. viewport 메타 태그 주입
    _ensure_viewport(soup)

    return str(soup)


def _add_preconnect_hints(soup: BeautifulSoup) -> None:
    """외부 도메인에 대한 rel="preconnect" 링크 힌트 추가."""
    external_domains: set[str] = set()

    for link in soup.find_all("link", href=True):
        href = link["href"]
        parsed = urlparse(href)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            external_domains.add(f"{parsed.scheme}://{parsed.netloc}")

    # 이미 존재하는 preconnect 도메인 제외
    existing_preconnects: set[str] = set()
    for link in soup.find_all("link", rel="preconnect"):
        if link.get("href"):
            existing_preconnects.add(link["href"])

    head = soup.find("head")
    for domain in external_domains - existing_preconnects:
        if head:
            new_link = soup.new_tag("link", rel="preconnect", href=domain)
            head.insert(0, new_link)


def _ensure_viewport(soup: BeautifulSoup) -> None:
    """viewport 메타 태그가 없으면 주입."""
    viewport = soup.find("meta", attrs={"name": "viewport"})
    if viewport:
        return

    head = soup.find("head")
    if not head:
        head = soup.new_tag("head")
        if soup.html:
            soup.html.insert(0, head)
        else:
            soup.insert(0, head)

    meta = soup.new_tag(
        "meta",
        attrs={
            "name": "viewport",
            "content": "width=device-width, initial-scale=1",
        },
    )
    head.insert(0, meta)


def validate_responsive(html: str) -> list[str]:
    """반응형 관련 문제점 목록 반환 (빈 리스트 = 정상).

    검증 항목:
    - viewport 메타 태그 존재 여부
    - <img> 태그에 loading="lazy" 존재 여부
    - 고정 width px 사용 여부 (인라인 스타일)
    """
    issues: list[str] = []
    soup = BeautifulSoup(html, "html.parser")

    # 1. viewport 메타 태그 검증
    if not soup.find("meta", attrs={"name": "viewport"}):
        issues.append("viewport 메타 태그가 없습니다")

    # 2. img lazy loading 검증
    for img in soup.find_all("img"):
        if img.get("loading") != "lazy":
            issues.append(f"img 태그에 loading='lazy'가 없습니다: {img.get('src', '?')}")

    # 3. 고정 width px 인라인 스타일 검증
    fixed_width_pattern = re.compile(r"width\s*:\s*\d+px")
    for tag in soup.find_all(style=True):
        if fixed_width_pattern.search(tag["style"]):
            issues.append(f"고정 width px 스타일 감지: {tag.name}")

    return issues
