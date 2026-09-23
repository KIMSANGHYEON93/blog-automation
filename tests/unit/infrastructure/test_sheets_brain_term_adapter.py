"""시트 'AI브레인용어' 탭 → BrainTerm 변환."""
from __future__ import annotations

from src.infrastructure.persistence.sheets_brain_term_adapter import (
    SheetsBrainTermAdapter,
    rows_to_terms,
)


class TestRowsToTerms:
    def test_컬럼을_매핑한다(self):
        terms = rows_to_terms([{
            "용어": "MCP", "별칭": "Model Context Protocol",
            "한줄정의": "모델과 도구를 잇는 프로토콜",
            "혼동포인트": "MCP ≠ 에이전트. 설명", "출처": "spec",
        }])
        assert len(terms) == 1
        t = terms[0]
        assert t.name == "MCP"
        assert t.definition == "모델과 도구를 잇는 프로토콜"
        assert t.aliases == ("Model Context Protocol",)
        assert t.confusion_target() == "에이전트"
        assert t.source == "spec"

    def test_용어가_빈_행은_버린다(self):
        rows = [{"용어": "", "한줄정의": "x"}, {"용어": "  ", "한줄정의": "y"},
                {"용어": "MCP", "한줄정의": "z"}]
        assert [t.name for t in rows_to_terms(rows)] == ["MCP"]

    def test_컬럼이_없어도_죽지_않는다(self):
        terms = rows_to_terms([{"용어": "MCP"}])
        assert terms[0].definition == ""
        assert terms[0].aliases == ()

    def test_숫자가_섞여도_문자열로_다룬다(self):
        terms = rows_to_terms([{"용어": 404, "한줄정의": 200}])
        assert terms[0].name == "404"


class TestAdapterContract:
    def test_포트를_구현한다(self):
        from src.domain.ports.brain_term_port import BrainTermPort

        assert issubclass(SheetsBrainTermAdapter, BrainTermPort)
