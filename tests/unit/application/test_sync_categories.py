"""SyncCategoriesUseCase tests."""
from __future__ import annotations

from src.application.use_cases.sync_categories import SyncCategoriesUseCase
from src.domain.ports.category_sync_port import CategorySyncPort, RemoteCategory
from src.domain.ports.site_profile_port import SiteProfilePort
from src.domain.value_objects.site_profile import CategoryMapping, SiteProfile


class StubProfilePort(SiteProfilePort):
    def __init__(self, profile: SiteProfile):
        self._profile = profile

    def load(self) -> SiteProfile:
        return self._profile

    def save(self, profile: SiteProfile) -> None:
        self._profile = profile


class StubSyncPort(CategorySyncPort):
    def __init__(self, categories: list[RemoteCategory]):
        self._categories = categories

    def fetch_categories(self) -> list[RemoteCategory]:
        return self._categories


def _profile(*cats: CategoryMapping) -> SiteProfile:
    return SiteProfile(blog_niche="test", default_category_id="0", categories=cats)


class TestSyncCategories:
    def test_all_synced(self):
        profile = _profile(
            CategoryMapping(name="용어", tistory_id="111"),
        )
        remote = [RemoteCategory(name="용어", category_id="111")]

        uc = SyncCategoriesUseCase(
            profile_port=StubProfilePort(profile),
            sync_port=StubSyncPort(remote),
        )
        result = uc.execute()

        assert result.synced is True
        assert len(result.diffs) == 0

    def test_new_remote_detected(self):
        profile = _profile(
            CategoryMapping(name="용어", tistory_id="111"),
        )
        remote = [
            RemoteCategory(name="용어", category_id="111"),
            RemoteCategory(name="비교", category_id="222"),
        ]

        uc = SyncCategoriesUseCase(
            profile_port=StubProfilePort(profile),
            sync_port=StubSyncPort(remote),
        )
        result = uc.execute()

        assert result.synced is False
        new = [d for d in result.diffs if d.diff_type == "new_remote"]
        assert len(new) == 1
        assert new[0].category_name == "비교"
        assert new[0].remote_id == "222"

    def test_missing_remote_detected(self):
        profile = _profile(
            CategoryMapping(name="용어", tistory_id="111"),
            CategoryMapping(name="가이드", tistory_id="333"),
        )
        remote = [RemoteCategory(name="용어", category_id="111")]

        uc = SyncCategoriesUseCase(
            profile_port=StubProfilePort(profile),
            sync_port=StubSyncPort(remote),
        )
        result = uc.execute()

        assert result.synced is False
        missing = [d for d in result.diffs if d.diff_type == "missing_remote"]
        assert len(missing) == 1
        assert missing[0].category_name == "가이드"

    def test_id_mismatch_detected(self):
        profile = _profile(
            CategoryMapping(name="용어", tistory_id="111"),
        )
        remote = [RemoteCategory(name="용어", category_id="999")]

        uc = SyncCategoriesUseCase(
            profile_port=StubProfilePort(profile),
            sync_port=StubSyncPort(remote),
        )
        result = uc.execute()

        assert result.synced is False
        mismatch = [d for d in result.diffs if d.diff_type == "id_mismatch"]
        assert len(mismatch) == 1
        assert mismatch[0].local_id == "111"
        assert mismatch[0].remote_id == "999"

    def test_auto_update_adds_new_categories(self):
        profile_port = StubProfilePort(_profile(
            CategoryMapping(name="용어", tistory_id="111"),
        ))
        remote = [
            RemoteCategory(name="용어", category_id="111"),
            RemoteCategory(name="비교", category_id="222"),
        ]

        uc = SyncCategoriesUseCase(
            profile_port=profile_port,
            sync_port=StubSyncPort(remote),
        )
        result = uc.execute(auto_update=True)

        assert result.updated is True
        updated = profile_port.load()
        names = [c.name for c in updated.categories]
        assert "비교" in names

    def test_mixed_diffs(self):
        profile = _profile(
            CategoryMapping(name="용어", tistory_id="111"),
            CategoryMapping(name="로컬전용", tistory_id="444"),
        )
        remote = [
            RemoteCategory(name="용어", category_id="999"),  # id_mismatch
            RemoteCategory(name="원격전용", category_id="555"),  # new_remote
        ]

        uc = SyncCategoriesUseCase(
            profile_port=StubProfilePort(profile),
            sync_port=StubSyncPort(remote),
        )
        result = uc.execute()

        assert result.synced is False
        types = {d.diff_type for d in result.diffs}
        assert types == {"new_remote", "missing_remote", "id_mismatch"}
