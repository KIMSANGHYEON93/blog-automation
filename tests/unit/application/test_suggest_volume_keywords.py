"""SuggestVolumeKeywordsUseCase — 검색량 기준 키워드 추천(네이버 검색광고 키워드 도구)."""
from __future__ import annotations

from src.application.use_cases.suggest_volume_keywords import (
    KeywordPillar,
    SuggestVolumeKeywordsUseCase,
)
from src.domain.entities.post import Post
from src.domain.ports.keyword_volume_port import KeywordVolumePort
from src.domain.value_objects.keyword_volume import KeywordVolume
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository

AI = KeywordPillar("AI 실무", hints=("챗GPT엑셀",), anchors=("GPT", "AI"))
TAX = KeywordPillar("경제", hints=("연말정산",), anchors=("연말정산",))


class FakeVolumes(KeywordVolumePort):
    def __init__(self, rows: dict[str, list[tuple[str, int]]]):
        self._rows, self.calls = rows, []

    def related(self, hints: list[str]) -> list[KeywordVolume]:
        self.calls.append(hints)
        return [KeywordVolume(k, n) for h in hints for k, n in self._rows.get(h, [])]


def _run(rows, existing=(), pillars=(AI, TAX), **kwargs):
    repo = InMemoryPostRepository(
        [Post(row_index=i + 2, keyword=k) for i, k in enumerate(existing)],
    )
    use_case = SuggestVolumeKeywordsUseCase(FakeVolumes(rows), [repo], list(pillars), **kwargs)
    return use_case.execute()


def test_검색량_범위_안에서_기준_단어가_들어간_것만_추천():
    result = _run({
        "챗GPT엑셀": [("챗GPT엑셀함수", 900), ("엑셀단축키", 5000), ("챗GPT", 900000),
                   ("GPT이미지", 50)],
        "연말정산": [("연말정산계산기", 3200), ("IRP계좌개설", 11000)],
    })
    assert [(s.keyword, s.monthly_searches, s.pillar) for s in result] == [
        ("챗GPT엑셀함수", 900, "AI 실무"), ("연말정산계산기", 3200, "경제"),
    ]


def test_띄어쓰기가_달라도_이미_쓴_키워드는_뺀다():
    # 검색광고 API는 띄어쓰기 없이 준다('챗GPT엑셀함수') — 시트는 띄어 쓴다
    result = _run({"챗GPT엑셀": [("챗GPT엑셀함수", 900), ("챗GPT엑셀수식", 700)]},
                  existing=["챗GPT 엑셀 함수 만들기"])
    assert [s.keyword for s in result] == ["챗GPT엑셀수식"]


def test_축마다_검색량_많은_순으로_상한까지():
    rows = {"챗GPT엑셀": [(f"GPT활용{i}", 400 + i) for i in range(5)]}
    result = _run(rows, per_pillar=2)
    assert [s.keyword for s in result] == ["GPT활용4", "GPT활용3"]


def test_같은_키워드는_한_번만():
    result = _run({"챗GPT엑셀": [("AI연말정산", 800)], "연말정산": [("AI연말정산", 800)]})
    assert [s.keyword for s in result] == ["AI연말정산"]
