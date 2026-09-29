"""KeywordVolumePort — 시드 키워드로 연관 키워드와 월간 검색량을 조회한다."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.value_objects.keyword_volume import KeywordVolume


class KeywordVolumePort(ABC):
    @abstractmethod
    def related(self, hints: list[str]) -> list[KeywordVolume]:
        """시드(힌트) 키워드들의 연관 키워드. 시드 자신도 포함될 수 있다."""
        ...
