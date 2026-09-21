"""Unit tests for KeywordMatcher domain service."""
from src.domain.services.keyword_matcher import (
    find_duplicate,
    is_covered_by_existing,
    keyword_overlap,
)


class TestKeywordOverlap:
    """토큰 기반 키워드 유사도 테스트."""

    def test_정확_일치(self):
        assert keyword_overlap("SSO란", "SSO란") == 1.0

    def test_대소문자_무시(self):
        assert keyword_overlap("sso란", "SSO란") == 1.0

    def test_단일_토큰_다른_키워드(self):
        assert keyword_overlap("SSO란", "AD란") == 0.0

    def test_다중_토큰_완전_일치(self):
        assert keyword_overlap("AWS SSO 설정", "AWS SSO 설정") == 1.0

    def test_다중_토큰_부분_일치(self):
        # "AWS SSO" vs "AWS IAM" → 1/2 = 0.5
        assert keyword_overlap("AWS SSO", "AWS IAM") == 0.5

    def test_다중_토큰_높은_유사도(self):
        # "AWS SSO 설정 방법" vs "AWS SSO 설정 가이드" → 3/4 = 0.75
        score = keyword_overlap("AWS SSO 설정 방법", "AWS SSO 설정 가이드")
        assert score == 0.75

    def test_완전히_다른_키워드(self):
        assert keyword_overlap("Docker 설치 방법", "Python 람다 함수") == 0.0

    def test_빈_문자열(self):
        assert keyword_overlap("", "") == 1.0

    def test_공백만_있는_경우(self):
        assert keyword_overlap("  ", "  ") == 1.0


class TestFindDuplicate:
    """중복 판정 통합 테스트."""

    def test_정확_일치_중복(self):
        is_dup, matched, score = find_duplicate(
            "SSO란", ["AD란", "SSO란", "VPN이란"],
        )
        assert is_dup is True
        assert matched == "SSO란"
        assert score == 1.0

    def test_유사도_초과_중복(self):
        is_dup, matched, score = find_duplicate(
            "AWS SSO 설정 방법",
            ["AWS SSO 설정 가이드", "Docker 설치"],
            threshold=0.7,
        )
        assert is_dup is True
        assert matched == "AWS SSO 설정 가이드"
        assert score == 0.75

    def test_유사도_미달_비중복(self):
        is_dup, matched, score = find_duplicate(
            "AWS SSO", ["AWS IAM", "Docker 설치"],
            threshold=0.7,
        )
        assert is_dup is False
        assert score == 0.5

    def test_빈_기존_목록(self):
        is_dup, matched, score = find_duplicate("SSO란", [])
        assert is_dup is False
        assert matched == ""
        assert score == 0.0

    def test_대소문자_무시_정확_일치(self):
        is_dup, matched, _ = find_duplicate("sso란", ["SSO란"])
        assert is_dup is True
        assert matched == "SSO란"

    def test_앞뒤_공백_무시(self):
        is_dup, matched, _ = find_duplicate("  SSO란  ", ["SSO란"])
        assert is_dup is True


class TestIsCoveredByExisting:
    """단일 토큰 키워드는 토큰 겹침 판정이 정확 일치만 보므로, 포함 관계를 따로 본다."""

    EXISTING = [
        "AADSTS50105 에러 해결: Azure AD 앱 할당 오류",
        "그룹 정책(GPO)이란? Active Directory GPO 설정 기초",
        "Kafka vs RabbitMQ 비교",
    ]

    def test_기존_키워드에_포함된_단일_토큰은_중복(self):
        assert is_covered_by_existing("aadsts50105", self.EXISTING) is True

    def test_기존_키워드에_포함된_복수_토큰도_중복(self):
        assert is_covered_by_existing("Kafka RabbitMQ", self.EXISTING) is True

    def test_토큰_하나라도_없으면_중복_아님(self):
        assert is_covered_by_existing("ad gpo", self.EXISTING) is False
        assert is_covered_by_existing("aadsts700016", self.EXISTING) is False

    def test_빈_키워드는_중복_아님(self):
        assert is_covered_by_existing("", self.EXISTING) is False
        assert is_covered_by_existing("   ", self.EXISTING) is False
