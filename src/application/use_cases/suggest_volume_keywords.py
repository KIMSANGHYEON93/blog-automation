"""SuggestVolumeKeywordsUseCase — 검색량 기준 키워드 추천(네이버 블로그 키워드 화면).

축(pillar)마다 시드로 연관 키워드를 받아, 월간 검색량 범위 안이고 축의 기준 단어가 들어간 것만
남긴다. 연관 키워드에는 엉뚱한 것이 섞인다('연말정산' → 'IRP계좌개설', 2026-09-29 실측).
광고 경쟁도(compIdx)는 거의 다 '높음'이라 블로그 경쟁과 무관해 쓰지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.application.use_cases.generate_keywords_from_terms import existing_keywords
from src.domain.ports.keyword_volume_port import KeywordVolumePort
from src.domain.ports.post_repository import PostRepository

HINTS_PER_CALL = 5  # 검색광고 키워드 도구 hintKeywords 상한


@dataclass(frozen=True)
class KeywordPillar:
    name: str
    hints: tuple[str, ...]
    anchors: tuple[str, ...]


@dataclass(frozen=True)
class VolumeSuggestion:
    keyword: str
    monthly_searches: int
    pillar: str


def _squash(keyword: str) -> str:
    """검색광고 API는 띄어쓰기 없이 준다('챗GPT엑셀함수') — 비교는 공백을 빼고 한다."""
    return "".join(keyword.lower().split())


class SuggestVolumeKeywordsUseCase:
    def __init__(
        self,
        port: KeywordVolumePort,
        repos: list[PostRepository],
        pillars: list[KeywordPillar],
        min_searches: int = 300,
        max_searches: int = 20000,
        per_pillar: int = 8,
    ):
        self._port = port
        self._repos = repos
        self._pillars = pillars
        self._range = (min_searches, max_searches)
        self._per_pillar = per_pillar

    def execute(self) -> list[VolumeSuggestion]:
        written = [_squash(k) for k in existing_keywords(self._repos)]
        seen: set[str] = set()
        result: list[VolumeSuggestion] = []
        for pillar in self._pillars:
            fresh = [s for s in self._candidates(pillar, written)
                     if _squash(s.keyword) not in seen]
            picked = sorted(fresh, key=lambda s: -s.monthly_searches)[: self._per_pillar]
            seen.update(_squash(s.keyword) for s in picked)
            result.extend(picked)
        return result

    def _candidates(self, pillar: KeywordPillar, written: list[str]) -> list[VolumeSuggestion]:
        low, high = self._range
        anchors = [a.lower() for a in pillar.anchors]
        found: dict[str, VolumeSuggestion] = {}
        for i in range(0, len(pillar.hints), HINTS_PER_CALL):
            for row in self._port.related(list(pillar.hints[i:i + HINTS_PER_CALL])):
                key = _squash(row.keyword)
                if not low <= row.monthly_searches <= high or key in found:
                    continue
                if not any(a in key for a in anchors):
                    continue
                # 이미 쓴 주제 — 띄어쓰기만 다르거나, 이미 쓴 더 긴 키워드에 포함된다
                if any(key in w or w in key for w in written):
                    continue
                found[key] = VolumeSuggestion(row.keyword, row.monthly_searches, pillar.name)
        return list(found.values())
