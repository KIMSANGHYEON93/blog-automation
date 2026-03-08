"""SiteProfilePort — Port interface for site profile persistence."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.value_objects.site_profile import SiteProfile


class SiteProfilePort(ABC):
    @abstractmethod
    def load(self) -> SiteProfile:
        """프로필 설정 로드."""
        ...

    @abstractmethod
    def save(self, profile: SiteProfile) -> None:
        """프로필 설정 저장."""
        ...
