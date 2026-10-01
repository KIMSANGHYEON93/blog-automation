"""html_transformer — HTML post-processing: lazy loading, nofollow, FAQ schema, validation."""
from __future__ import annotations

import logging
import re
from html import escape

logger = logging.getLogger(__name__)


def extract_first_image_url(html: str) -> str:
    """HTML 본문에서 첫 번째 <img> src URL 추출 — ThumbnailService 위임."""
    from src.domain.services.thumbnail_service import ThumbnailService
    return ThumbnailService.extract_first_image_url(html)


def add_lazy_loading(html_text: str) -> str:
    """<img> 태그에 loading="lazy" 속성을 추가. 첫 번째 이미지는 제외 (LCP candidate)."""
    if not html_text:
        return html_text
    count = 0

    def _replace_img(match: re.Match) -> str:
        nonlocal count
        count += 1
        tag: str = match.group(0)
        if count == 1:
            # 첫 번째 이미지: LCP candidate이므로 lazy loading 미적용
            return tag
        return '<img loading="lazy" ' + tag[5:]

    return re.sub(r"<img\s(?!.*loading=)", _replace_img, html_text)


def add_nofollow_to_external_links(html_text: str, blog_name: str) -> str:
    """외부 링크 <a> 태그에 rel="nofollow noopener" target="_blank" 추가.

    내부 링크 (같은 블로그 도메인)는 제외.
    """
    if not html_text:
        return html_text

    internal_pattern = re.compile(
        rf'https?://({re.escape(blog_name)}\.tistory\.com|tistory\.com)',
        re.IGNORECASE,
    )

    def _process_anchor(match: re.Match) -> str:
        tag: str = match.group(0)
        href_match = re.search(r'href="([^"]*)"', tag)
        if not href_match:
            return tag
        href = href_match.group(1)
        # 내부 링크, 앵커, 빈 href는 건드리지 않음
        if not href or href.startswith('#') or internal_pattern.search(href):
            return tag
        # 이미 rel이 있으면 건드리지 않음
        if 'rel=' in tag:
            return tag
        # target="_blank"과 rel 추가
        tag = tag.rstrip('>')
        if 'target=' not in tag:
            tag += ' target="_blank"'
        tag += ' rel="nofollow noopener">'
        return tag

    return re.sub(r'<a\s[^>]*>', _process_anchor, html_text)


def validate_html(html_text: str) -> bool:
    """HTML 변환 결과를 검증 — HtmlValidationService 위임."""
    from src.domain.services.html_validation import HtmlValidationService

    svc = HtmlValidationService()
    result = svc.validate(html_text)

    # 기존 로깅 유지
    for error in result.errors:
        logger.warning(f"HTML 검증: {error}")
    for warning in result.warnings:
        logger.warning(f"HTML 검증 경고: {warning}")

    # FAQ LD+JSON 스키마 존재 여부 (info only — 주입 전 호출이므로 통과)
    if html_text and '<script type="application/ld+json">' not in html_text:
        logger.info("validate_html: FAQ LD+JSON 스키마 미포함 (faq_schema 없는 글)")

    return result.passed


SUMMARY_LEAD_CLASS = "post-summary"

# 본문 맨 앞의 텍스트 없는 블록(히어로 figure, 이미지만 있는 p)과 제목 h1
_LEADING_BLOCK = re.compile(
    r"\s*(?:<figure\b[^>]*>.*?</figure>"
    r"|<p>\s*(?:<a\b[^>]*>\s*)?<img\b[^>]*>\s*(?:</a>\s*)?</p>"
    r"|<h1\b[^>]*>.*?</h1>)",
    re.IGNORECASE | re.DOTALL,
)


def insert_summary_lead(html_text: str, summary: str) -> str:
    """요약문을 본문 첫 텍스트 블록으로 삽입.

    Tistory는 post API에 description 필드가 없고 본문 첫 텍스트로 meta description을
    자동 생성한다. 요약을 목차/도입부보다 앞(히어로 이미지·H1 제목 뒤)에 두어
    검색 스니펫이 '목차…' 대신 요약문이 되게 한다.
    """
    import html as html_lib

    normalized = " ".join((summary or "").split())
    if not html_text or not normalized or f'class="{SUMMARY_LEAD_CLASS}"' in html_text:
        return html_text

    pos = 0
    while True:
        match = _LEADING_BLOCK.match(html_text, pos)
        if not match:
            break
        pos = match.end()

    lead = f'<p class="{SUMMARY_LEAD_CLASS}">{html_lib.escape(normalized, quote=False)}</p>'
    return html_text[:pos] + lead + html_text[pos:]


def append_faq_schema(body_markdown: str, faq_ld_json: str) -> str:
    """본문 하단에 FAQ LD+JSON 스키마를 추가.

    JSON 유효성 검증 후 재직렬화하여 </script> 탈출 공격을 방지한다.
    """
    import json

    try:
        parsed = json.loads(faq_ld_json)
        safe_json = json.dumps(parsed, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"FAQ 스키마 JSON 파싱 실패 — 스키마 삽입 건너뜀: {e}")
        return body_markdown

    schema_block = (
        '\n\n<script type="application/ld+json">\n'
        f'{safe_json}\n'
        '</script>'
    )
    return body_markdown + schema_block


_CTA_TEXT = "IT·AI 실무 글을 네이버 블로그에도 올립니다. 이웃 추가하고 새 글 받아 보세요."
_CTA_BOX_STYLE = (
    "margin:48px 0 8px;padding:20px 24px;border:1px solid #e9ecef;"
    "border-radius:8px;background:#f8f9fa;text-align:center"
)
_CTA_TEXT_STYLE = "margin:0 0 12px;font-size:16px;color:#1a1a2e"
_CTA_BUTTON_STYLE = (
    "display:inline-block;padding:10px 20px;border-radius:6px;background:#03c75a;"
    "color:#fff;font-weight:700;text-decoration:none"
)


def append_naver_cta(html_text: str, url: str) -> str:
    """글 맨 끝에 네이버 블로그 이웃 추가 블록. url이 비면 그대로(설정 없음)."""
    if not url:
        return html_text
    return (
        f'{html_text}\n<div class="naver-cta" style="{_CTA_BOX_STYLE}">'
        f'<p style="{_CTA_TEXT_STYLE}">{_CTA_TEXT}</p>'
        f'<a href="{escape(url)}" target="_blank" rel="noopener" style="{_CTA_BUTTON_STYLE}">'
        f"네이버 블로그 이웃 추가</a></div>"
    )
