"""RegisterKeywordUseCase — 관리자가 직접 넣는 키워드를 '대기'로 등록.

중복 기준은 자동 발굴·n8n Check Duplicate와 같다. 기준이 갈리면 등록한 키워드를
Pipeline A가 중복으로 버려 자리만 낭비한다.
"""
from __future__ import annotations

from src.application.use_cases.discover_keywords import DUPLICATE_THRESHOLD
from src.application.use_cases.generate_keywords_from_terms import existing_keywords
from src.domain.ports.post_repository import PostRepository
from src.domain.services.keyword_matcher import find_duplicate, is_covered_by_existing


class DuplicateKeywordError(Exception):
    def __init__(self, keyword: str, matched: str):
        super().__init__(f"'{keyword}'은(는) 이미 있는 '{matched}'와 겹칩니다")
        self.matched = matched


class RegisterKeywordUseCase:
    def __init__(self, repo: PostRepository, other_repos: list[PostRepository] | None = None):
        self._repo = repo
        self._other_repos = other_repos or []

    def register(self, keyword: str) -> int:
        keyword = keyword.strip()
        pool = existing_keywords([self._repo, *self._other_repos])
        is_dup, matched, _ = find_duplicate(keyword, pool, DUPLICATE_THRESHOLD)
        if not is_dup and is_covered_by_existing(keyword, pool):
            tokens = set(keyword.lower().split())
            matched = next(k for k in pool if tokens <= set(k.lower().split()))
            is_dup = True
        if is_dup:
            raise DuplicateKeywordError(keyword, matched)
        return self._repo.add_keyword_row(keyword)
