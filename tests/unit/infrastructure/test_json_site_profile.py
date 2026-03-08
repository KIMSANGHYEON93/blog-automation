"""JsonSiteProfileAdapter tests."""
import json
from pathlib import Path

from src.domain.value_objects.site_profile import CategoryMapping, SiteProfile
from src.infrastructure.persistence.json_site_profile import JsonSiteProfileAdapter


def _write_profile(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "site_profile.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


class TestJsonSiteProfileAdapter:
    def test_load_full(self, tmp_path):
        data = {
            "blog_niche": "B2B IT",
            "default_category_id": "966384",
            "categories": [
                {
                    "name": "용어",
                    "tistory_id": "991463",
                    "aliases": ["개념"],
                    "keyword_patterns": ["란$"],
                },
            ],
        }
        path = _write_profile(tmp_path, data)
        adapter = JsonSiteProfileAdapter(path)
        profile = adapter.load()

        assert profile.blog_niche == "B2B IT"
        assert profile.default_category_id == "966384"
        assert len(profile.categories) == 1
        assert profile.categories[0].name == "용어"
        assert profile.categories[0].aliases == ("개념",)
        assert profile.categories[0].keyword_patterns == ("란$",)

    def test_load_empty_categories(self, tmp_path):
        data = {"blog_niche": "test", "default_category_id": "0", "categories": []}
        path = _write_profile(tmp_path, data)
        adapter = JsonSiteProfileAdapter(path)
        profile = adapter.load()

        assert profile.categories == ()

    def test_load_missing_optional_fields(self, tmp_path):
        data = {
            "categories": [
                {"name": "기타", "tistory_id": "111"},
            ],
        }
        path = _write_profile(tmp_path, data)
        adapter = JsonSiteProfileAdapter(path)
        profile = adapter.load()

        assert profile.blog_niche == ""
        assert profile.default_category_id == "0"
        assert profile.categories[0].aliases == ()
        assert profile.categories[0].keyword_patterns == ()

    def test_save_and_reload(self, tmp_path):
        path = tmp_path / "site_profile.json"
        adapter = JsonSiteProfileAdapter(path)

        profile = SiteProfile(
            blog_niche="테스트",
            default_category_id="999",
            categories=(
                CategoryMapping(
                    name="A", tistory_id="1",
                    aliases=("a1",), keyword_patterns=("패턴$",),
                ),
            ),
        )
        adapter.save(profile)

        loaded = adapter.load()
        assert loaded.blog_niche == "테스트"
        assert loaded.default_category_id == "999"
        assert len(loaded.categories) == 1
        assert loaded.categories[0].name == "A"
        assert loaded.categories[0].aliases == ("a1",)

    def test_save_overwrites(self, tmp_path):
        path = tmp_path / "site_profile.json"
        adapter = JsonSiteProfileAdapter(path)

        p1 = SiteProfile(
            blog_niche="v1", default_category_id="0", categories=(),
        )
        adapter.save(p1)

        p2 = SiteProfile(
            blog_niche="v2", default_category_id="1", categories=(),
        )
        adapter.save(p2)

        loaded = adapter.load()
        assert loaded.blog_niche == "v2"
