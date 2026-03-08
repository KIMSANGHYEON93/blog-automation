"""JsonSiteProfile — SiteProfilePort adapter using JSON file."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from src.domain.ports.site_profile_port import SiteProfilePort
from src.domain.value_objects.site_profile import CategoryMapping, SiteProfile

logger = logging.getLogger(__name__)


class JsonSiteProfileAdapter(SiteProfilePort):
    """site_profile.json 파일 기반 SiteProfile 어댑터."""

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def load(self) -> SiteProfile:
        """JSON 파일에서 SiteProfile 로드."""
        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)

        categories = tuple(
            CategoryMapping(
                name=c["name"],
                tistory_id=c["tistory_id"],
                aliases=tuple(c.get("aliases", [])),
                keyword_patterns=tuple(c.get("keyword_patterns", [])),
            )
            for c in data.get("categories", [])
        )

        return SiteProfile(
            blog_niche=data.get("blog_niche", ""),
            default_category_id=data.get("default_category_id", "0"),
            categories=categories,
        )

    def save(self, profile: SiteProfile) -> None:
        """SiteProfile을 JSON 파일로 저장."""
        data = {
            "blog_niche": profile.blog_niche,
            "default_category_id": profile.default_category_id,
            "categories": [
                {
                    "name": c.name,
                    "tistory_id": c.tistory_id,
                    "aliases": list(c.aliases),
                    "keyword_patterns": list(c.keyword_patterns),
                }
                for c in profile.categories
            ],
        }

        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"site_profile.json 저장: {self._path}")
