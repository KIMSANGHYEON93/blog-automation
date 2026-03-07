"""KeywordSuggestion VO 테스트."""
import pytest

from src.domain.value_objects.keyword_suggestion import KeywordSuggestion


class TestKeywordSuggestion:
    def test_기본값(self):
        ks = KeywordSuggestion(keyword="테스트")
        assert ks.keyword == "테스트"
        assert ks.impressions == 0
        assert ks.ctr == 0.0

    def test_frozen(self):
        ks = KeywordSuggestion(keyword="테스트")
        with pytest.raises(AttributeError):
            ks.keyword = "changed"  # type: ignore[misc]

    def test_opportunity_score_계산(self):
        """impressions × (1 - ctr)."""
        score = KeywordSuggestion.calculate_opportunity(
            impressions=100, ctr=0.02,
        )
        assert abs(score - 98.0) < 0.01

    def test_opportunity_score_CTR_높으면_낮음(self):
        """CTR이 높으면 기회 점수가 낮음 (이미 잘 클릭됨)."""
        low_ctr = KeywordSuggestion.calculate_opportunity(100, 0.01)
        high_ctr = KeywordSuggestion.calculate_opportunity(100, 0.10)
        assert low_ctr > high_ctr
