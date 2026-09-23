"""BrainTermPort — AI-Brain 볼트 용어 조회 인터페이스."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.value_objects.brain_term import BrainTerm


class BrainTermPort(ABC):
    @abstractmethod
    def fetch_terms(self) -> list[BrainTerm]:
        """용어 카드 전체 조회.

        Returns:
            BrainTerm 리스트. 용어명이 빈 행은 제외한다.
        """
        ...
