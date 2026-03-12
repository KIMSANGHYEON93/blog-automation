"""InternalLinkEnricher — shared Application Service for internal link enrichment."""
from __future__ import annotations

from dataclasses import replace

from src.domain.entities.post import Post
from src.domain.services.internal_link_service import InternalLinkService


class InternalLinkEnricher:
    """발행/수정 시 공통으로 사용하는 내부 링크 강화 서비스.

    InternalLinkService(Domain)를 주입받아, 관련 글 HTML 생성과
    keyword→URL 매핑을 post에 첨부한다.
    """

    def __init__(self, link_service: InternalLinkService) -> None:
        self._link_service = link_service

    def identify_hubs(self, published: list[Post]) -> list[Post]:
        """Hub post 식별을 InternalLinkService에 위임."""
        return self._link_service.identify_hubs(published)

    def enrich_with_related_links(
        self, post: Post, published: list[Post], hubs: list[Post],
    ) -> None:
        """관련 글 HTML을 본문 끝에 추가."""
        if not post.content or not post.content.has_body():
            return

        related = self._link_service.select_links(post, published, hubs)
        if not related:
            return

        items = "".join(
            f'<li style="margin:8px 0;">'
            f'<a href="{p.published_url}">{p.keyword}</a></li>'
            for p in related[:5]
        )
        html = (
            "\n\n<hr>\n"
            '<div style="margin-top:30px;padding:20px;'
            'background:#f8f9fa;border-radius:8px;">'
            "<h3>관련 글</h3>"
            f'<ul style="list-style:none;padding:0;">{items}</ul>'
            "</div>"
        )
        post.content = replace(
            post.content,
            body_markdown=(post.content.body_markdown or "") + html,
        )

    def attach_internal_link_map(
        self, post: Post, published: list[Post],
    ) -> None:
        """발행 완료 포스트의 keyword→URL 매핑을 post에 첨부.

        tistory_editor가 HTML 변환 후 inject_internal_links()에 전달.
        """
        if not post.content or not post.content.has_body():
            return
        link_map = {
            p.keyword: p.published_url
            for p in published
            if p.keyword and p.published_url
            and p.row_index != post.row_index
        }
        if link_map:
            post.internal_link_map = link_map
