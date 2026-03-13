"""IndexingRecord — Value Object for tracking Google indexing status."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class IndexingStatus(Enum):
    """Google 색인 상태."""
    INDEXED = "indexed"
    DISCOVERED = "discovered"
    CRAWLED = "crawled"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class IndexingRecord:
    """색인 상태 추적 도메인 모델."""

    status: IndexingStatus
    verdict: str
    checked_at: datetime

    @property
    def is_indexed(self) -> bool:
        """색인 완료 여부."""
        return self.status == IndexingStatus.INDEXED

    @property
    def needs_resubmission(self) -> bool:
        """재제출 필요 여부 (DISCOVERED 또는 UNKNOWN)."""
        return self.status in (IndexingStatus.DISCOVERED, IndexingStatus.UNKNOWN)
