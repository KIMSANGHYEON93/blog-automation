"""PostRepository — Port interface (defined by Domain)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.post import Post


class PostRepository(ABC):
    @abstractmethod
    def find_pending(self, limit: int = 5) -> list[Post]:
        """Find posts with PENDING status."""
        ...

    @abstractmethod
    def save(self, post: Post) -> None:
        """Persist post state changes."""
        ...

    @abstractmethod
    def find_stuck(self) -> list[Post]:
        """Find posts stuck in PUBLISHING status."""
        ...
