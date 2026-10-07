"""PostContent.reference_urls — 시트 '참고자료' 칸(JSON 목록 또는 줄바꿈)에서 주소만 뽑는다."""
from src.domain.value_objects.post_content import PostContent


def test_JSON_목록에서_주소를_뽑는다():
    c = PostContent(references='["https://a.com/x","https://b.com"]')
    assert c.reference_urls() == ["https://a.com/x", "https://b.com"]


def test_비어_있으면_빈_목록():
    assert PostContent(references="[]").reference_urls() == []
    assert PostContent().reference_urls() == []
