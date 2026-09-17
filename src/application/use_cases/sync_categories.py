"""SyncCategoriesUseCase — Tistory 카테고리와 site_profile.json 동기화."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.domain.ports.category_sync_port import CategorySyncPort, RemoteCategory
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


def _leaf(name: str) -> str:
    """Tistory label은 '상위/하위' 전체 경로 — 마지막 구간이 로컬 카테고리명에 대응."""
    return name.rsplit("/", 1)[-1]


def _root(name: str) -> str:
    return name.split("/", 1)[0]


def _find_by_leaf(
    name: str, remote_cats: list[RemoteCategory], roots: set[str],
) -> RemoteCategory | None:
    candidates = [r for r in remote_cats if _leaf(r.name) == name]
    in_roots = [r for r in candidates if _root(r.name) in roots]
    preferred = in_roots or candidates
    return preferred[0] if preferred else None


def _diff_categories(
    local_cats: list[CategoryMapping], remote_cats: list[RemoteCategory],
) -> list[CategoryDiff]:
    """ID 우선 매칭 → 마지막 이름으로 ID 불일치 판정 → 관리 루트 안의 신규 원격만 보고."""
    remote_by_id = {r.category_id: r for r in remote_cats}
    hierarchical = any("/" in r.name for r in remote_cats)

    matched_ids = {c.tistory_id for c in local_cats if c.tistory_id in remote_by_id}
    roots = {_root(remote_by_id[rid].name) for rid in matched_ids}

    diffs: list[CategoryDiff] = []
    for local in local_cats:
        if local.tistory_id in remote_by_id:
            continue
        remote = _find_by_leaf(local.name, remote_cats, roots)
        if remote is None:
            diffs.append(CategoryDiff(
                category_name=local.name, diff_type="missing_remote", local_id=local.tistory_id,
            ))
            continue
        matched_ids.add(remote.category_id)
        roots.add(_root(remote.name))
        diffs.append(CategoryDiff(
            category_name=local.name, diff_type="id_mismatch",
            local_id=local.tistory_id, remote_id=remote.category_id,
        ))

    # 하위 카테고리를 가진 원격 카테고리는 컨테이너이므로 신규 대상에서 제외
    parents = {r.name.rsplit("/", 1)[0] for r in remote_cats if "/" in r.name}
    for remote in remote_cats:
        if remote.category_id in matched_ids or remote.name in parents:
            continue
        if hierarchical and _root(remote.name) not in roots:
            continue  # 블로그의 다른 주제(개인 카테고리 등)는 관리 대상 아님
        diffs.append(CategoryDiff(
            category_name=_leaf(remote.name), diff_type="new_remote", remote_id=remote.category_id,
        ))
    return diffs


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

        result = SyncResult()
        result.diffs.extend(_diff_categories(list(profile.categories), remote_cats))
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
