"""SiteProfile — Value Objects for blog site configuration."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryMapping:
    """단일 카테고리 매핑 정보."""

    name: str
    tistory_id: str
    aliases: tuple[str, ...] = ()
    keyword_patterns: tuple[str, ...] = ()
    view_channel: str = ""

    def matches_keyword(self, keyword: str) -> bool:
        """키워드가 이 카테고리의 패턴과 매칭되는지 확인."""
        if not keyword or not self.keyword_patterns:
            return False
        return any(re.search(pattern, keyword) for pattern in self.keyword_patterns)


@dataclass(frozen=True)
class SiteProfile:
    """블로그 사이트 프로필 설정. 카테고리 매핑 + 키워드 분류 규칙 포함."""

    blog_niche: str
    default_category_id: str
    categories: tuple[CategoryMapping, ...]
    default_view_channel: str = ""

    def resolve_category_id(self, category_name: str) -> str:
        """카테고리 이름을 Tistory 카테고리 ID로 변환.

        매칭 순서: 정확매칭 → 별칭 → 부분매칭 → default.
        """
        if not category_name:
            return self.default_category_id

        name = category_name.strip()
        if not name:
            return self.default_category_id

        # 1. 정확 매칭
        for cat in self.categories:
            if cat.name == name:
                return cat.tistory_id

        # 2. 별칭 매칭
        name_lower = name.lower()
        for cat in self.categories:
            for alias in cat.aliases:
                if alias.lower() == name_lower:
                    return cat.tistory_id

        # 3. 부분 매칭 (카테고리 이름/별칭이 입력에 포함되거나 그 반대)
        for cat in self.categories:
            if cat.name.lower() in name_lower or name_lower in cat.name.lower():
                return cat.tistory_id
            for alias in cat.aliases:
                a = alias.lower()
                if a in name_lower or name_lower in a:
                    return cat.tistory_id

        return self.default_category_id

    def resolve_view_channel(self, category_name: str) -> str:
        """카테고리 이름에 대응하는 홈주제(viewChannel) 값 반환."""
        if not category_name:
            return self.default_view_channel

        name = category_name.strip()
        if not name:
            return self.default_view_channel

        for cat in self.categories:
            if cat.name == name:
                return cat.view_channel or self.default_view_channel
        name_lower = name.lower()
        for cat in self.categories:
            for alias in cat.aliases:
                if alias.lower() == name_lower:
                    return cat.view_channel or self.default_view_channel
        for cat in self.categories:
            if cat.name.lower() in name_lower or name_lower in cat.name.lower():
                return cat.view_channel or self.default_view_channel
            for alias in cat.aliases:
                a = alias.lower()
                if a in name_lower or name_lower in a:
                    return cat.view_channel or self.default_view_channel

        return self.default_view_channel

    def classify_keyword(self, keyword: str) -> str | None:
        """키워드 패턴 매칭으로 카테고리 이름 반환. 매칭 없으면 None."""
        if not keyword:
            return None
        for cat in self.categories:
            if cat.matches_keyword(keyword):
                return cat.name
        return None
