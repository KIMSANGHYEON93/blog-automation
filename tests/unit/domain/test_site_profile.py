"""SiteProfile + CategoryMapping value object tests."""
from src.domain.value_objects.site_profile import CategoryMapping, SiteProfile


def _sample_categories() -> tuple[CategoryMapping, ...]:
    return (
        CategoryMapping(
            name="용어",
            tistory_id="991463",
            aliases=("용어정리", "개념"),
            keyword_patterns=("란$", "이란$", "뜻$", "의미$"),
        ),
        CategoryMapping(
            name="비교",
            tistory_id="966384",
            aliases=(),
            keyword_patterns=("vs ", "비교$", "차이$"),
        ),
        CategoryMapping(
            name="트러블슈팅",
            tistory_id="966384",
            aliases=("에러", "오류"),
            keyword_patterns=("에러$", "오류$", "해결$", "안될때$"),
        ),
        CategoryMapping(
            name="가이드",
            tistory_id="966384",
            aliases=("튜토리얼",),
            keyword_patterns=("방법$", "설정$", "설치$", "가이드$"),
        ),
        CategoryMapping(
            name="트렌드",
            tistory_id="966384",
            aliases=("동향",),
            keyword_patterns=("트렌드$", "전망$"),
        ),
    )


def _sample_profile() -> SiteProfile:
    return SiteProfile(
        blog_niche="B2B IT 블로그",
        default_category_id="966384",
        categories=_sample_categories(),
    )


# --- CategoryMapping tests ---


class TestCategoryMapping:
    def test_frozen(self):
        cat = CategoryMapping(name="용어", tistory_id="123")
        try:
            cat.name = "변경"  # type: ignore[misc]
            raise AssertionError("should be frozen")
        except AttributeError:
            pass

    def test_matches_keyword_with_pattern(self):
        cat = CategoryMapping(
            name="용어", tistory_id="991463",
            keyword_patterns=("란$", "이란$"),
        )
        assert cat.matches_keyword("API란") is True
        assert cat.matches_keyword("REST API이란") is True

    def test_matches_keyword_no_match(self):
        cat = CategoryMapping(
            name="용어", tistory_id="991463",
            keyword_patterns=("란$",),
        )
        assert cat.matches_keyword("API 설정 방법") is False

    def test_matches_keyword_empty(self):
        cat = CategoryMapping(name="용어", tistory_id="991463")
        assert cat.matches_keyword("API란") is False

    def test_matches_keyword_empty_keyword(self):
        cat = CategoryMapping(
            name="용어", tistory_id="991463",
            keyword_patterns=("란$",),
        )
        assert cat.matches_keyword("") is False

    def test_default_aliases_empty(self):
        cat = CategoryMapping(name="용어", tistory_id="991463")
        assert cat.aliases == ()
        assert cat.keyword_patterns == ()


# --- SiteProfile.resolve_category_id tests ---


class TestSiteProfileResolve:
    def test_exact_match(self):
        p = _sample_profile()
        assert p.resolve_category_id("용어") == "991463"

    def test_alias_match(self):
        p = _sample_profile()
        assert p.resolve_category_id("용어정리") == "991463"
        assert p.resolve_category_id("에러") == "966384"

    def test_alias_case_insensitive(self):
        profile = SiteProfile(
            blog_niche="test",
            default_category_id="0",
            categories=(
                CategoryMapping(name="Guide", tistory_id="111", aliases=("TUTORIAL",)),
            ),
        )
        assert profile.resolve_category_id("tutorial") == "111"

    def test_partial_match(self):
        p = _sample_profile()
        # "트러블슈팅 가이드" contains "트러블슈팅"
        assert p.resolve_category_id("트러블슈팅 가이드") == "966384"

    def test_partial_match_reverse(self):
        """카테고리 이름이 입력보다 긴 경우 — 입력이 카테고리에 포함."""
        profile = SiteProfile(
            blog_niche="test",
            default_category_id="0",
            categories=(
                CategoryMapping(name="트러블슈팅", tistory_id="555"),
            ),
        )
        assert profile.resolve_category_id("트러블") == "555"

    def test_empty_name_returns_default(self):
        p = _sample_profile()
        assert p.resolve_category_id("") == "966384"

    def test_whitespace_only_returns_default(self):
        p = _sample_profile()
        assert p.resolve_category_id("   ") == "966384"

    def test_no_match_returns_default(self):
        p = _sample_profile()
        assert p.resolve_category_id("알수없는카테고리") == "966384"


# --- SiteProfile.classify_keyword tests ---


class TestSiteProfileClassify:
    def test_classify_term(self):
        p = _sample_profile()
        assert p.classify_keyword("REST API란") == "용어"

    def test_classify_comparison(self):
        p = _sample_profile()
        assert p.classify_keyword("Redis vs Memcached") == "비교"
        assert p.classify_keyword("Kafka 차이") == "비교"

    def test_classify_troubleshoot(self):
        p = _sample_profile()
        assert p.classify_keyword("CORS 에러") == "트러블슈팅"
        assert p.classify_keyword("Docker 안될때") == "트러블슈팅"

    def test_classify_guide(self):
        p = _sample_profile()
        assert p.classify_keyword("Nginx 설치") == "가이드"
        assert p.classify_keyword("Git 설정") == "가이드"

    def test_classify_trend(self):
        p = _sample_profile()
        assert p.classify_keyword("2026 AI 트렌드") == "트렌드"

    def test_classify_no_match(self):
        p = _sample_profile()
        assert p.classify_keyword("파이썬 프로그래밍") is None

    def test_classify_empty(self):
        p = _sample_profile()
        assert p.classify_keyword("") is None

    def test_frozen_profile(self):
        p = _sample_profile()
        try:
            p.blog_niche = "변경"  # type: ignore[misc]
            raise AssertionError("should be frozen")
        except AttributeError:
            pass
