"""SheetRowData value object tests."""
import pytest

from src.domain.value_objects.sheet_row_data import SheetRowData


class TestSheetRowData:
    def test_create_with_required_fields(self):
        row = SheetRowData(row_index=2, keyword="SSO란")
        assert row.row_index == 2
        assert row.keyword == "SSO란"
        assert row.category == ""

    def test_create_with_all_fields(self):
        row = SheetRowData(
            row_index=5,
            keyword="SAML vs OIDC",
            category="IT 비교",
            content_type="comparison",
            status="발행대기",
            generated_title="SAML vs OIDC 비교",
            generated_body="# 본문",
        )
        assert row.status == "발행대기"
        assert row.generated_title == "SAML vs OIDC 비교"

    def test_is_immutable(self):
        row = SheetRowData(row_index=1, keyword="test")
        with pytest.raises(AttributeError):
            row.keyword = "변경"
