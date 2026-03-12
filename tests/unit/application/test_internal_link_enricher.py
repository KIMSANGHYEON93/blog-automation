"""Unit tests for InternalLinkEnricher — Application Service."""
from __future__ import annotations

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.domain.entities.post import Post
from src.domain.services.internal_link_service import InternalLinkService
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus


def _make_published(row: int, keyword: str, url: str,
                    category: str = "IT",
                    link_kws: list[str] | None = None) -> Post:
    return Post(
        row_index=row,
        keyword=keyword,
        category=category,
        status=PostStatus.PUBLISHED,
        content=PostContent(title=keyword, body_markdown="본문"),
        published_url=url,
        internal_link_keywords=link_kws or [],
    )


def _make_pending(row: int, keyword: str, category: str = "IT",
                  body: str = "## 내용\n본문") -> Post:
    return Post(
        row_index=row,
        keyword=keyword,
        category=category,
        status=PostStatus.PENDING,
        content=PostContent(title=keyword, body_markdown=body),
    )


class TestEnrichWithRelatedLinks:
    """enrich_with_related_links() 테스트."""

    def test_관련_글_HTML_삽입(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        post = _make_pending(10, "AD란")
        pub1 = _make_published(1, "SSO란", "https://test.tistory.com/1")
        pub2 = _make_published(2, "LDAP란", "https://test.tistory.com/2")
        hubs = enricher.identify_hubs([pub1, pub2])

        enricher.enrich_with_related_links(post, [pub1, pub2], hubs)

        assert "관련 글" in post.content.body_markdown
        assert "SSO란" in post.content.body_markdown

    def test_content_None이면_무시(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        post = Post(row_index=10, keyword="AD란", status=PostStatus.PENDING)

        enricher.enrich_with_related_links(post, [], [])
        assert post.content is None

    def test_빈_본문이면_무시(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        post = Post(
            row_index=10, keyword="AD란", status=PostStatus.PENDING,
            content=PostContent(title="AD란", body_markdown=""),
        )

        enricher.enrich_with_related_links(post, [], [])
        assert post.content.body_markdown == ""

    def test_발행글_없으면_관련글_미삽입(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        post = _make_pending(10, "AD란")

        enricher.enrich_with_related_links(post, [], [])

        assert "관련 글" not in post.content.body_markdown


class TestAttachInternalLinkMap:
    """attach_internal_link_map() 테스트."""

    def test_keyword_URL_매핑_첨부(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        post = _make_pending(10, "AD란")
        pub1 = _make_published(1, "SSO란", "https://test.tistory.com/1")
        pub2 = _make_published(2, "LDAP란", "https://test.tistory.com/2")

        enricher.attach_internal_link_map(post, [pub1, pub2])

        assert post.internal_link_map == {
            "SSO란": "https://test.tistory.com/1",
            "LDAP란": "https://test.tistory.com/2",
        }

    def test_자기자신_제외(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        post = _make_pending(1, "AD란")
        pub_self = _make_published(1, "AD란", "https://test.tistory.com/1")
        pub_other = _make_published(2, "SSO란", "https://test.tistory.com/2")

        enricher.attach_internal_link_map(post, [pub_self, pub_other])

        assert "AD란" not in post.internal_link_map
        assert "SSO란" in post.internal_link_map

    def test_content_None이면_무시(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        post = Post(row_index=10, keyword="AD란", status=PostStatus.PENDING)

        enricher.attach_internal_link_map(post, [])
        assert post.internal_link_map is None


class TestIdentifyHubs:
    """identify_hubs() 위임 테스트."""

    def test_허브_식별_위임(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        pub1 = _make_published(1, "SSO란", "https://test.tistory.com/1")
        pub2 = _make_published(
            2, "LDAP란", "https://test.tistory.com/2",
            link_kws=["SSO"],
        )
        pub3 = _make_published(
            3, "AD란", "https://test.tistory.com/3",
            link_kws=["SSO"],
        )

        hubs = enricher.identify_hubs([pub1, pub2, pub3])

        hub_keywords = [h.keyword for h in hubs]
        assert "SSO란" in hub_keywords
