"""CategoryClassificationService — 키워드 기반 카테고리 자동 분류."""
from __future__ import annotations

from src.domain.value_objects.site_profile import SiteProfile


class CategoryClassificationService:
    """키워드 패턴 매칭으로 카테고리 자동 분류. Stateless."""

    def classify(self, keyword: str, profile: SiteProfile) -> str | None:
        """키워드에 맞는 카테고리 이름 반환. 매칭 없으면 None."""
        return profile.classify_keyword(keyword)
