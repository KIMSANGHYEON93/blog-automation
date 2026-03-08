"""CategoryClassificationService tests."""
from src.domain.services.category_classification import CategoryClassificationService
from src.domain.value_objects.site_profile import CategoryMapping, SiteProfile


def _profile() -> SiteProfile:
    return SiteProfile(
        blog_niche="test",
        default_category_id="0",
        categories=(
            CategoryMapping(
                name="용어", tistory_id="111",
                keyword_patterns=("란$", "이란$", "뜻$"),
            ),
            CategoryMapping(
                name="비교", tistory_id="222",
                keyword_patterns=("vs ", "비교$", "차이$"),
            ),
            CategoryMapping(
                name="가이드", tistory_id="333",
                keyword_patterns=("방법$", "설정$", "설치$"),
            ),
        ),
    )


class TestCategoryClassificationService:
    def test_classify_term_keyword(self):
        svc = CategoryClassificationService()
        assert svc.classify("API란", _profile()) == "용어"

    def test_classify_comparison_keyword(self):
        svc = CategoryClassificationService()
        assert svc.classify("Redis vs Memcached", _profile()) == "비교"

    def test_classify_no_match_returns_none(self):
        svc = CategoryClassificationService()
        assert svc.classify("파이썬 프로그래밍", _profile()) is None

    def test_classify_empty_keyword_returns_none(self):
        svc = CategoryClassificationService()
        assert svc.classify("", _profile()) is None
