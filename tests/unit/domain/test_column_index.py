"""ColumnIndex value object tests."""
from src.domain.value_objects.column_index import ColumnIndex


class TestColumnIndex:
    def test_default_mapping(self):
        ci = ColumnIndex()
        assert ci.no == 1
        assert ci.keyword == 2
        assert ci.status == 10
        assert ci.internal_link_keywords == 19

    def test_has_19_columns(self):
        """A~S = 19 columns."""
        from dataclasses import fields
        assert len(fields(ColumnIndex)) == 19

    def test_is_immutable(self):
        import pytest
        ci = ColumnIndex()
        with pytest.raises(AttributeError):
            ci.keyword = 99
