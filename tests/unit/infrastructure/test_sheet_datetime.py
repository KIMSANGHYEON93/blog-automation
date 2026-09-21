"""시트 R열(발행일시) 파싱 — 실제 시트에 섞여 있는 형식들."""
from __future__ import annotations

from datetime import datetime

from src.infrastructure.persistence.google_sheets_repo import parse_sheet_datetime


class TestParseSheetDatetime:
    def test_표준_형식(self):
        assert parse_sheet_datetime("2026-09-17 21:04:28") == datetime(2026, 9, 17, 21, 4, 28)

    def test_시가_한자리인_값(self):
        assert parse_sheet_datetime("2026-03-08 0:18:04") == datetime(2026, 3, 8, 0, 18, 4)

    def test_분까지만_있는_값(self):
        assert parse_sheet_datetime("2026-03-08 09:18") == datetime(2026, 3, 8, 9, 18)

    def test_날짜만_있는_값(self):
        assert parse_sheet_datetime("2026-03-08") == datetime(2026, 3, 8)

    def test_앞뒤_공백_허용(self):
        assert parse_sheet_datetime("  2026-03-08  ") == datetime(2026, 3, 8)

    def test_해석_불가한_값은_None(self):
        # 시트 일련번호, 빈값 등은 덮어쓰지 않도록 None
        assert parse_sheet_datetime("46104.63329") is None
        assert parse_sheet_datetime("") is None
        assert parse_sheet_datetime("   ") is None
        assert parse_sheet_datetime("발행완료") is None
