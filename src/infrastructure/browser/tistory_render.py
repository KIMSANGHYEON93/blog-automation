"""티스토리 본문 HTML 변환 — 발행·수정 발행·대시보드 미리보기가 같이 쓴다(브라우저 없음)."""
from __future__ import annotations

import logging

from src.domain.entities.post import Post
from src.infrastructure.browser import html_transformer, markdown_converter
from src.infrastructure.seo.html_optimizer import optimize_html
from src.infrastructure.seo.inline_styler import apply_inline_styles
from src.infrastructure.seo.internal_linker import inject_internal_links

logger = logging.getLogger(__name__)


class _LinkPost:
    def __init__(self, keyword: str, url: str):
        self.keyword = keyword
        self.published_url = url


def render_tistory_html(post: Post, blog_name: str, cta_url: str = "") -> str:
    """마크다운 본문 → 에디터에 넣을 최종 HTML. post.content가 있어야 한다."""
    content = post.content
    assert content is not None
    html_body = markdown_converter.convert_markdown_to_html(content.body_markdown or "")
    # 요약 문단: Tistory는 본문 첫 텍스트로 meta description을 자동 생성
    html_body = html_transformer.insert_summary_lead(html_body, content.meta_description)
    html_body = html_transformer.add_lazy_loading(html_body)
    html_body = html_transformer.add_nofollow_to_external_links(html_body, blog_name)

    if post.internal_link_map:
        link_posts = [_LinkPost(kw, url) for kw, url in post.internal_link_map.items()]
        keywords = content.internal_keyword_list()
        prev_len = len(html_body)
        html_body = inject_internal_links(html_body, keywords, link_posts)
        logger.info(
            f"내부 링크 삽입: keywords={len(keywords)}, "
            f"published={len(link_posts)}, body: {prev_len}→{len(html_body)}자"
        )

    if not html_transformer.validate_html(html_body):
        logger.warning("HTML 변환 검증 실패 — 그대로 진행")

    faq_ld_json = content.faq_ld_json()
    if faq_ld_json:
        html_body = html_transformer.append_faq_schema(html_body, faq_ld_json)

    # 반응형 + 성능 최적화 (img lazy/decoding, iframe lazy, preconnect)
    html_body = optimize_html(html_body)
    return apply_inline_styles(html_body)
