"""fill_keyword_meta SerpAPI 호출 조건 — 무료 플랜(월 250건) 소진 방지."""
import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "update_dashboard.py"
_spec = importlib.util.spec_from_file_location("update_dashboard", _SCRIPT)
dashboard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dashboard)


def _row(keyword: str, difficulty: str = "", priority: str = "") -> list:
    row = [""] * 31
    row[dashboard.IDX_KEYWORD] = keyword
    row[dashboard.IDX_SEARCH_VOL] = "500"
    row[dashboard.IDX_CPC] = "1000"
    row[dashboard.IDX_DIFFICULTY] = difficulty
    row[dashboard.IDX_PRIORITY] = priority
    return row


class _FakeSheet:
    def __init__(self, rows):
        self._rows = [["header"] * 31, *rows]
        self.updated = []

    def get_all_values(self):
        return self._rows

    def update_cells(self, cells):
        self.updated.extend(cells)


class _FakeSpreadsheet:
    def __init__(self, rows):
        self.sheet1 = _FakeSheet(rows)


@pytest.fixture
def serp_calls(monkeypatch):
    calls = []

    def fake_fetch(api_key, keyword):
        calls.append(keyword)
        return {"organic_results": [], "ads": [], "search_information": {"total_results": 0}}

    monkeypatch.setenv("SERPAPI_KEY", "test-key")
    monkeypatch.setattr(dashboard, "fetch_serp", fake_fetch)
    monkeypatch.setattr(dashboard.time, "sleep", lambda _s: None)
    return calls


class TestFillKeywordMetaSerpBudget:
    def test_난이도가_이미_있으면_SERP_호출_안함(self, serp_calls):
        rows = [_row("A", "중", "A"), _row("B", "상", ""), _row("C", "하", "S")]
        dashboard.fill_keyword_meta(_FakeSpreadsheet(rows))
        assert serp_calls == []

    def test_난이도가_비어있으면_SERP_호출(self, serp_calls):
        rows = [_row("A", "중", "A"), _row("B", "", "")]
        dashboard.fill_keyword_meta(_FakeSpreadsheet(rows))
        assert serp_calls == ["B"]

    def test_실행당_SERP_호출_상한(self, serp_calls):
        rows = [_row(f"kw{i}") for i in range(dashboard.MAX_SERP_CALLS_PER_RUN + 15)]
        dashboard.fill_keyword_meta(_FakeSpreadsheet(rows))
        assert len(serp_calls) == dashboard.MAX_SERP_CALLS_PER_RUN

    def test_상한_초과_행도_난이도는_추정값으로_채움(self, serp_calls):
        rows = [_row(f"kw{i}") for i in range(dashboard.MAX_SERP_CALLS_PER_RUN + 3)]
        sheet = _FakeSpreadsheet(rows)
        dashboard.fill_keyword_meta(sheet)
        diff_rows = {c.row for c in sheet.sheet1.updated if c.col == dashboard.IDX_DIFFICULTY + 1}
        assert len(diff_rows) == len(rows)
