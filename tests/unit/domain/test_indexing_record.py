"""IndexingRecord Value Object tests."""
from datetime import datetime

from src.domain.value_objects.indexing_record import IndexingRecord, IndexingStatus


class TestIndexingRecord:
    def test_is_indexed_true(self):
        r = IndexingRecord(
            status=IndexingStatus.INDEXED,
            verdict="PASS",
            checked_at=datetime(2026, 3, 9, 10, 0),
        )
        assert r.is_indexed is True

    def test_is_indexed_false_when_crawled(self):
        r = IndexingRecord(
            status=IndexingStatus.CRAWLED,
            verdict="",
            checked_at=datetime(2026, 3, 9, 10, 0),
        )
        assert r.is_indexed is False

    def test_needs_resubmission_discovered(self):
        r = IndexingRecord(
            status=IndexingStatus.DISCOVERED,
            verdict="",
            checked_at=datetime(2026, 3, 9, 10, 0),
        )
        assert r.needs_resubmission is True

    def test_needs_resubmission_unknown(self):
        r = IndexingRecord(
            status=IndexingStatus.UNKNOWN,
            verdict="",
            checked_at=datetime(2026, 3, 9, 10, 0),
        )
        assert r.needs_resubmission is True

    def test_no_resubmission_when_indexed(self):
        r = IndexingRecord(
            status=IndexingStatus.INDEXED,
            verdict="PASS",
            checked_at=datetime(2026, 3, 9, 10, 0),
        )
        assert r.needs_resubmission is False

    def test_frozen_immutable(self):
        r = IndexingRecord(
            status=IndexingStatus.INDEXED,
            verdict="PASS",
            checked_at=datetime(2026, 3, 9, 10, 0),
        )
        try:
            r.status = IndexingStatus.CRAWLED  # type: ignore[misc]
            raise AssertionError("Should raise FrozenInstanceError")
        except AttributeError:
            pass
