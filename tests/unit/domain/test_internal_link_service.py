"""Unit tests for InternalLinkService — hub-spoke internal link model."""
from __future__ import annotations

from src.domain.entities.post import Post
from src.domain.services.internal_link_service import InternalLinkService
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus


def _pub(row: int, keyword: str, category: str = "IT",
         url: str = "", keywords: list[str] | None = None) -> Post:
    """Helper to create a published post."""
    return Post(
        row_index=row,
        keyword=keyword,
        category=category,
        status=PostStatus.PUBLISHED,
        content=PostContent(title=keyword, body_markdown="본문"),
        published_url=url or f"https://test.tistory.com/{row}",
        internal_link_keywords=keywords or [],
    )


def _pending(row: int, keyword: str, category: str = "IT",
             keywords: list[str] | None = None) -> Post:
    """Helper to create a pending post."""
    return Post(
        row_index=row,
        keyword=keyword,
        category=category,
        status=PostStatus.PENDING,
        content=PostContent(title=keyword, body_markdown="본문"),
        internal_link_keywords=keywords or [],
    )


class TestIdentifyHubs:
    def setup_method(self):
        self.svc = InternalLinkService()

    def test_empty_posts_returns_empty(self):
        assert self.svc.identify_hubs([]) == []

    def test_no_keywords_returns_empty(self):
        posts = [_pub(1, "SSO란"), _pub(2, "LDAP란")]
        assert self.svc.identify_hubs(posts) == []

    def test_single_hub_identified(self):
        """SSO란 is mentioned in other posts' keywords → becomes a hub."""
        posts = [
            _pub(1, "SSO란", keywords=[]),
            _pub(2, "LDAP란", keywords=["SSO"]),
            _pub(3, "OAuth란", keywords=["SSO"]),
        ]
        hubs = self.svc.identify_hubs(posts)
        assert len(hubs) == 1
        assert hubs[0].row_index == 1  # SSO란

    def test_multiple_hubs_sorted_by_mentions(self):
        """Posts with most mentions appear first."""
        posts = [
            _pub(1, "SSO란", keywords=["LDAP"]),
            _pub(2, "LDAP란", keywords=["SSO"]),
            _pub(3, "OAuth란", keywords=["SSO", "LDAP"]),
            _pub(4, "SAML란", keywords=["SSO"]),
        ]
        hubs = self.svc.identify_hubs(posts)
        # SSO란 mentioned by 3 posts (2,3,4), LDAP란 by 2 (1,3)
        assert hubs[0].row_index == 1  # SSO란 — most mentions
        assert hubs[1].row_index == 2  # LDAP란

    def test_max_3_hubs(self):
        """Even with many candidates, only 3 hubs are returned."""
        posts = [
            _pub(1, "A란", keywords=[]),
            _pub(2, "B란", keywords=[]),
            _pub(3, "C란", keywords=[]),
            _pub(4, "D란", keywords=[]),
            _pub(5, "E란", keywords=["A", "B", "C", "D"]),
        ]
        hubs = self.svc.identify_hubs(posts)
        assert len(hubs) <= 3

    def test_self_reference_excluded(self):
        """A post doesn't count as mentioning itself."""
        posts = [
            _pub(1, "SSO란", keywords=["SSO"]),
        ]
        hubs = self.svc.identify_hubs(posts)
        assert len(hubs) == 0

    def test_posts_without_url_excluded_from_hubs(self):
        """Posts without published_url cannot be hubs."""
        posts = [
            _pub(1, "SSO란", url="", keywords=[]),
            _pub(2, "LDAP란", keywords=["SSO"]),
        ]
        # SSO란 has no URL → not a valid hub candidate
        posts[0].published_url = ""
        hubs = self.svc.identify_hubs(posts)
        assert len(hubs) == 0


class TestSelectLinks:
    def setup_method(self):
        self.svc = InternalLinkService()

    def test_empty_published_returns_empty(self):
        target = _pending(10, "AD란")
        assert self.svc.select_links(target, [], []) == []

    def test_self_excluded(self):
        target = _pending(1, "AD란")
        published = [_pub(1, "AD란"), _pub(2, "SSO란")]
        result = self.svc.select_links(target, published, [])
        assert all(p.row_index != 1 for p in result)

    def test_max_5_links(self):
        target = _pending(10, "AD란", keywords=["SSO", "LDAP"])
        published = [_pub(i, f"글{i}", keywords=["SSO"]) for i in range(1, 10)]
        result = self.svc.select_links(target, published, [])
        assert len(result) <= 5

    def test_no_url_excluded(self):
        """Posts without published_url are excluded from results."""
        target = _pending(10, "AD란")
        no_url = Post(
            row_index=1, keyword="SSO란", category="IT",
            status=PostStatus.PUBLISHED, published_url="",
            content=PostContent(title="SSO란", body_markdown="본문"),
        )
        published = [no_url, _pub(2, "LDAP란")]
        result = self.svc.select_links(target, published, [])
        assert all(p.row_index != 1 for p in result)

    def test_hub_to_hub_priority(self):
        """Hub posts link to other hubs first."""
        hub1 = _pub(1, "SSO란", keywords=["LDAP"])
        hub2 = _pub(2, "LDAP란", keywords=["SSO"])
        normal = _pub(3, "일반 글", keywords=[])
        hubs = [hub1, hub2]

        target = _pending(1, "SSO란", keywords=["LDAP"])
        target.row_index = 1  # target is hub1
        result = self.svc.select_links(target, [hub1, hub2, normal], hubs)
        # hub2 (LDAP란) should be first due to hub-to-hub bonus
        assert result[0].row_index == 2

    def test_keyword_overlap_scoring(self):
        """Posts with more keyword overlap rank higher."""
        target = _pending(10, "SSO란", keywords=["LDAP", "OAuth", "SAML"])
        high_overlap = _pub(1, "LDAP란", keywords=["LDAP", "OAuth", "SAML"])
        low_overlap = _pub(2, "기타", keywords=["Docker"])
        result = self.svc.select_links(target, [high_overlap, low_overlap], [])
        assert result[0].row_index == 1

    def test_same_category_preferred_over_different(self):
        """Same category gets higher score in fallback."""
        target = _pending(10, "AD란", category="보안")
        same = _pub(1, "SSO란", category="보안")
        diff = _pub(2, "Docker란", category="DevOps")
        result = self.svc.select_links(target, [same, diff], [])
        assert result[0].row_index == 1

    def test_fallback_category_when_no_keywords(self):
        """When no keywords, category-based fallback still works."""
        target = _pending(10, "AD란", category="IT", keywords=[])
        same1 = _pub(1, "SSO란", category="IT", keywords=[])
        same2 = _pub(2, "LDAP란", category="IT", keywords=[])
        diff = _pub(3, "Docker란", category="DevOps", keywords=[])
        result = self.svc.select_links(target, [same1, same2, diff], [])
        # same category posts should come first
        assert result[0].category == "IT"
        assert result[1].category == "IT"

    def test_hub_link_priority(self):
        """Target's keywords mentioning a hub gives that hub a bonus."""
        hub = _pub(1, "SSO란", keywords=[])
        normal = _pub(2, "기타 글", category="IT", keywords=[])
        hubs = [hub]

        target = _pending(10, "AD란", category="IT", keywords=["SSO"])
        result = self.svc.select_links(target, [hub, normal], hubs)
        assert result[0].row_index == 1  # hub gets priority


class TestSelectLinksEdgeCases:
    def setup_method(self):
        self.svc = InternalLinkService()

    def test_all_same_score_stable_order(self):
        """When scores are equal, original order is preserved."""
        target = _pending(10, "AD란", keywords=[])
        posts = [_pub(i, f"글{i}", keywords=[]) for i in range(1, 4)]
        result = self.svc.select_links(target, posts, [])
        assert [p.row_index for p in result] == [1, 2, 3]

    def test_case_insensitive_keyword_matching(self):
        """Keyword matching should be case insensitive."""
        target = _pending(10, "SSO란", keywords=["ldap", "oauth"])
        post = _pub(1, "LDAP란", keywords=["LDAP", "OAUTH"])
        result = self.svc.select_links(target, [post], [])
        assert len(result) == 1
