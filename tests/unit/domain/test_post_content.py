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

    def test_create_with_thumbnail_url(self):
        c = PostContent(
            title="제목",
            body_markdown="본문",
            thumbnail_url="https://images.unsplash.com/photo-test",
        )
        assert c.thumbnail_url == "https://images.unsplash.com/photo-test"

    def test_thumbnail_url_defaults_to_empty(self):
        c = PostContent(title="제목", body_markdown="본문")
        assert c.thumbnail_url == ""

    def test_is_immutable(self):
        c = PostContent(title="제목", body_markdown="본문")
        with pytest.raises(AttributeError):
            c.title = "변경"


class TestFaqLdJson:
    """faq_ld_json() 메서드 단위 테스트."""

    def test_faq_ld_json_정상_변환(self):
        """2건 FAQ → FAQPage schema + mainEntity 2건."""
        import json

        faq_data = json.dumps([
            {"question": "Q1", "answer": "A1"},
            {"question": "Q2", "answer": "A2"},
        ])
        c = PostContent(title="제목", body_markdown="본문", faq_schema=faq_data)
        result = c.faq_ld_json()
        parsed = json.loads(result)
        assert parsed["@type"] == "FAQPage"
        assert parsed["@context"] == "https://schema.org"
        assert len(parsed["mainEntity"]) == 2
        assert parsed["mainEntity"][0]["@type"] == "Question"
        assert parsed["mainEntity"][0]["name"] == "Q1"
        assert parsed["mainEntity"][0]["acceptedAnswer"]["text"] == "A1"
        assert parsed["mainEntity"][1]["name"] == "Q2"

    def test_faq_ld_json_빈_스키마(self):
        """faq_schema="" → 빈 문자열 반환."""
        c = PostContent(title="제목", body_markdown="본문", faq_schema="")
        assert c.faq_ld_json() == ""

    def test_faq_ld_json_잘못된_JSON(self):
        """파싱 불가 문자열 → 빈 문자열 (예외 없음)."""
        c = PostContent(title="제목", body_markdown="본문", faq_schema="{invalid json!!")
        assert c.faq_ld_json() == ""

    def test_faq_ld_json_빈_배열(self):
        """'[]' → 빈 문자열."""
        c = PostContent(title="제목", body_markdown="본문", faq_schema="[]")
        assert c.faq_ld_json() == ""

    def test_faq_ld_json_필드_누락(self):
        """question만 있고 answer 없음 → 해당 항목 건너뜀."""
        import json

        faq_data = json.dumps([
            {"question": "Q1"},
            {"question": "Q2", "answer": "A2"},
        ])
        c = PostContent(title="제목", body_markdown="본문", faq_schema=faq_data)
        result = c.faq_ld_json()
        parsed = json.loads(result)
        assert len(parsed["mainEntity"]) == 1
        assert parsed["mainEntity"][0]["name"] == "Q2"

    def test_faq_ld_json_한국어_보존(self):
        """한국어 질답 → ensure_ascii=False 확인."""
        import json

        faq_data = json.dumps([
            {"question": "한국어 질문입니다", "answer": "한국어 답변입니다"},
        ], ensure_ascii=False)
        c = PostContent(title="제목", body_markdown="본문", faq_schema=faq_data)
        result = c.faq_ld_json()
        assert "한국어 질문입니다" in result
        assert "한국어 답변입니다" in result
        # ensure_ascii=False 확인: 유니코드 이스케이프가 아닌 한국어 원문이 포함
        assert "\\u" not in result
