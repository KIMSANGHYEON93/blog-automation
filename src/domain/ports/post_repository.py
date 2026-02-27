"""PostRepository — Port interface (defined by Domain)."""
from abc import ABC, abstractmethod
from typing import List

from src.domain.entities.post import Post


class PostRepository(ABC):
    @abstractmethod
    def find_pending(self, limit: int = 5) -> List[Post]:
        """Find posts with PENDING status."""
        ...

    @abstractmethod
    def save(self, post: Post) -> None:
        """Persist post state changes."""
        ...

    @abstractmethod
    def find_stuck(self) -> List[Post]:
        """Find posts stuck in PUBLISHING status."""
        ...
