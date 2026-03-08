"""SyncCategoriesUseCase — Tistory 카테고리와 site_profile.json 동기화."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.domain.ports.category_sync_port import CategorySyncPort
from src.domain.ports.site_profile_port import SiteProfilePort
from src.domain.value_objects.site_profile import CategoryMapping

logger = logging.getLogger(__name__)


@dataclass
class CategoryDiff:
    """카테고리 동기화 차이 항목."""

    category_name: str
    diff_type: str  # "new_remote", "missing_remote", "id_mismatch"
    local_id: str = ""
    remote_id: str = ""


@dataclass
class SyncResult:
    """카테고리 동기화 결과 DTO."""

    diffs: list[CategoryDiff] = field(default_factory=list)
    synced: bool = True
    updated: bool = False


class SyncCategoriesUseCase:
    """Tistory 원격 카테고리와 로컬 site_profile.json 비교/동기화."""

    def __init__(
        self,
        profile_port: SiteProfilePort,
        sync_port: CategorySyncPort,
    ):
        self._profile_port = profile_port
        self._sync_port = sync_port

    def execute(self, auto_update: bool = False) -> SyncResult:
        profile = self._profile_port.load()
        remote_cats = self._sync_port.fetch_categories()

        # 로컬 카테고리 이름 → ID 매핑
        local_map: dict[str, str] = {c.name: c.tistory_id for c in profile.categories}
        # 원격 카테고리 이름 → ID 매핑
        remote_map: dict[str, str] = {r.name: r.category_id for r in remote_cats}

        result = SyncResult()

        # 1. 원격에만 있는 카테고리
        for name, rid in remote_map.items():
            if name not in local_map:
                result.diffs.append(CategoryDiff(
                    category_name=name,
                    diff_type="new_remote",
                    remote_id=rid,
                ))

        # 2. 로컬에만 있는 카테고리
        for name in local_map:
            if name not in remote_map:
                result.diffs.append(CategoryDiff(
                    category_name=name,
                    diff_type="missing_remote",
                    local_id=local_map[name],
                ))

        # 3. ID 불일치
        for name in local_map:
            if name in remote_map and local_map[name] != remote_map[name]:
                result.diffs.append(CategoryDiff(
                    category_name=name,
                    diff_type="id_mismatch",
                    local_id=local_map[name],
                    remote_id=remote_map[name],
                ))

        result.synced = len(result.diffs) == 0

        # 자동 갱신: 신규 원격 카테고리 추가 + ID 불일치 수정
        if auto_update and not result.synced:
            new_cats = list(profile.categories)

            for diff in result.diffs:
                if diff.diff_type == "new_remote":
                    new_cats.append(CategoryMapping(
                        name=diff.category_name,
                        tistory_id=diff.remote_id,
                    ))
                    logger.info(f"카테고리 추가: {diff.category_name} (ID={diff.remote_id})")
                elif diff.diff_type == "id_mismatch":
                    for i, c in enumerate(new_cats):
                        if c.name == diff.category_name:
                            new_cats[i] = CategoryMapping(
                                name=c.name,
                                tistory_id=diff.remote_id,
                                aliases=c.aliases,
                                keyword_patterns=c.keyword_patterns,
                            )
                            logger.info(
                                f"카테고리 ID 수정: {diff.category_name} "
                                f"{diff.local_id} → {diff.remote_id}"
                            )
                            break

            from src.domain.value_objects.site_profile import SiteProfile

            updated_profile = SiteProfile(
                blog_niche=profile.blog_niche,
                default_category_id=profile.default_category_id,
                categories=tuple(new_cats),
            )
            self._profile_port.save(updated_profile)
            result.updated = True

        return result
