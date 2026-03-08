"""CategorySyncPort — Port interface for Tistory category fetching."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RemoteCategory:
    """Tistory 원격 카테고리 정보."""

    name: str
    category_id: str
    parent: str = ""
    entry_count: int = 0


class CategorySyncPort(ABC):
    @abstractmethod
    def fetch_categories(self) -> list[RemoteCategory]:
        """Tistory에서 카테고리 목록 가져오기."""
        ...
