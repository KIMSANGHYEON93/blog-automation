"""PostContent value object tests — TDD RED phase."""
import pytest

from src.domain.value_objects.post_content import PostContent


class TestPostContent:
    def test_create_with_all_fields(self):
        c = PostContent(
            title="제목",
            body_markdown="본문 내용",
            meta_description="설명",
            faq_schema="[]",
        )
        assert c.title == "제목"
        assert c.body_markdown == "본문 내용"
        assert c.meta_description == "설명"
        assert c.faq_schema == "[]"

    def test_has_body_true(self):
        c = PostContent(title="제목", body_markdown="본문 있음")
        assert c.has_body() is True

    def test_has_body_false_when_empty(self):
        c = PostContent(title="제목", body_markdown="")
        assert c.has_body() is False

    def test_has_body_false_when_none(self):
        c = PostContent(title="제목", body_markdown=None)
        assert c.has_body() is False

    def test_has_body_false_when_whitespace(self):
        c = PostContent(title="제목", body_markdown="   \n  ")
        assert c.has_body() is False

    def test_title_or_fallback_returns_title(self):
        c = PostContent(title="실제 제목", body_markdown="본문")
        assert c.title_or_fallback("대체") == "실제 제목"

    def test_title_or_fallback_when_empty(self):
        c = PostContent(title="", body_markdown="본문")
        assert c.title_or_fallback("대체 제목") == "대체 제목"

    def test_title_or_fallback_when_none(self):
        c = PostContent(title=None, body_markdown="본문")
        assert c.title_or_fallback("키워드") == "키워드"

    def test_tag_list_with_tags(self):
        c = PostContent(title="제목", body_markdown="본문", tags="SSO,AD,인증")
        assert c.tag_list() == ["SSO", "AD", "인증"]

    def test_tag_list_empty_string(self):
        c = PostContent(title="제목", body_markdown="본문", tags="")
        assert c.tag_list() == []

    def test_tag_list_with_whitespace(self):
        c = PostContent(title="제목", body_markdown="본문", tags=" SSO , AD , ")
        assert c.tag_list() == ["SSO", "AD"]

    def test_is_immutable(self):
        c = PostContent(title="제목", body_markdown="본문")
        with pytest.raises(AttributeError):
            c.title = "변경"
