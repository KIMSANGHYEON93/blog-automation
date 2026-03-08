"""ClassifyCategoryUseCase — PENDING 포스트에 카테고리 자동 분류."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.domain.ports.post_repository import PostRepository
from src.domain.ports.site_profile_port import SiteProfilePort
from src.domain.services.category_classification import CategoryClassificationService

logger = logging.getLogger(__name__)


@dataclass
class ClassifyResult:
    """카테고리 분류 결과 DTO."""

    classified: int = 0
    skipped: int = 0
    details: list[tuple[str, str]] = field(default_factory=list)


class ClassifyCategoryUseCase:
    """카테고리가 비어있는 PENDING 포스트에 키워드 패턴으로 카테고리 자동 분류."""

    def __init__(
        self,
        repo: PostRepository,
        profile_port: SiteProfilePort,
    ):
        self._repo = repo
        self._profile_port = profile_port
        self._service = CategoryClassificationService()

    def execute(self, limit: int = 50) -> ClassifyResult:
        profile = self._profile_port.load()
        posts = self._repo.find_pending(limit=limit)
        result = ClassifyResult()

        for post in posts:
            if post.category and post.category.strip():
                result.skipped += 1
                continue

            category = self._service.classify(post.keyword, profile)
            if category:
                self._repo.save_category(post.row_index, category)
                result.classified += 1
                result.details.append((post.keyword, category))
                logger.info(f"자동 분류: '{post.keyword}' → {category}")
            else:
                result.skipped += 1

        return result
