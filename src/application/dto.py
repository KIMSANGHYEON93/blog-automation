"""Application DTOs — Data Transfer Objects for use case results."""
from dataclasses import dataclass


@dataclass
class PublishStatsDTO:
    published: int
    failed: int
    skipped: int
    total: int

    @classmethod
    def from_stats(cls, stats) -> "PublishStatsDTO":
        total = stats.published + stats.failed + stats.skipped
        return cls(
            published=stats.published,
            failed=stats.failed,
            skipped=stats.skipped,
            total=total,
        )
