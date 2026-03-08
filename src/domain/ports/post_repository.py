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

    @abstractmethod
    def find_failed(self) -> list[Post]:
        """Find posts with FAILED status."""
        ...

    @abstractmethod
    def find_published(self, limit: int = 50) -> list[Post]:
        """발행완료 상태의 포스트 목록 (내부 링크용)."""
        ...

    @abstractmethod
    def find_cwv_unchecked(self, limit: int = 10) -> list[Post]:
        """발행완료 상태이면서 CWV 미점검 포스트 목록."""
        ...

    @abstractmethod
    def save_cwv_record(
        self, row_index: int,
        lcp: float, cls_score: float,
    ) -> None:
        """CWV 측정 결과를 시트에 기록."""
        ...

    @abstractmethod
    def find_revision_pending(self, limit: int = 5) -> list[Post]:
        """Find posts with REVISION_PENDING status."""
        ...

    @abstractmethod
    def find_revising_stuck(self) -> list[Post]:
        """Find posts stuck in REVISING status."""
        ...

    @abstractmethod
    def find_all(self) -> list[Post]:
        """전체 포스트 조회 (상태 대시보드용)."""
        ...

    @abstractmethod
    def save_category(self, row_index: int, category: str) -> None:
        """카테고리 값을 저장."""
        ...
