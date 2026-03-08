"""ClassifyCategoryUseCase tests."""
from __future__ import annotations

from src.application.use_cases.classify_category import ClassifyCategoryUseCase
from src.domain.entities.post import Post
from src.domain.ports.site_profile_port import SiteProfilePort
from src.domain.value_objects.site_profile import CategoryMapping, SiteProfile
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


class StubProfilePort(SiteProfilePort):
    def __init__(self):
        self._profile = SiteProfile(
            blog_niche="test",
            default_category_id="0",
            categories=(
                CategoryMapping(
                    name="용어", tistory_id="111",
                    keyword_patterns=("란$", "이란$"),
                ),
                CategoryMapping(
                    name="비교", tistory_id="222",
                    keyword_patterns=("vs ", "비교$"),
                ),
            ),
        )

    def load(self) -> SiteProfile:
        return self._profile

    def save(self, profile: SiteProfile) -> None:
        self._profile = profile


def _post(keyword: str, category: str = "", row_index: int = 2) -> Post:
    return Post(row_index=row_index, keyword=keyword, category=category)


class TestClassifyCategory:
    def test_classify_empty_category_posts(self):
        repo = InMemoryPostRepository([
            _post("API란", row_index=2),
            _post("Redis vs Memcached", row_index=3),
        ])
        uc = ClassifyCategoryUseCase(repo=repo, profile_port=StubProfilePort())
        result = uc.execute()

        assert result.classified == 2
        assert result.skipped == 0
        assert ("API란", "용어") in result.details
        assert ("Redis vs Memcached", "비교") in result.details

    def test_skip_already_categorized(self):
        repo = InMemoryPostRepository([
            _post("API란", category="용어", row_index=2),
        ])
        uc = ClassifyCategoryUseCase(repo=repo, profile_port=StubProfilePort())
        result = uc.execute()

        assert result.classified == 0
        assert result.skipped == 1

    def test_no_match_skipped(self):
        repo = InMemoryPostRepository([
            _post("파이썬 프로그래밍", row_index=2),
        ])
        uc = ClassifyCategoryUseCase(repo=repo, profile_port=StubProfilePort())
        result = uc.execute()

        assert result.classified == 0
        assert result.skipped == 1

    def test_mixed_posts(self):
        repo = InMemoryPostRepository([
            _post("API란", row_index=2),            # classify → 용어
            _post("Kafka 설치", category="가이드", row_index=3),  # skip (has category)
            _post("파이썬 기초", row_index=4),       # skip (no match)
        ])
        uc = ClassifyCategoryUseCase(repo=repo, profile_port=StubProfilePort())
        result = uc.execute()

        assert result.classified == 1
        assert result.skipped == 2

    def test_no_pending_posts(self):
        repo = InMemoryPostRepository([])
        uc = ClassifyCategoryUseCase(repo=repo, profile_port=StubProfilePort())
        result = uc.execute()

        assert result.classified == 0
        assert result.skipped == 0
