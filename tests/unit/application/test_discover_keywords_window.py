"""키워드 발굴 조회 기간 — 28일 창은 노출이 흩어져 임계치를 못 넘는다.

2026-09-23 실측 (kimsanghyeon.tistory.com, GSC 500행):
    28일 창 → 노출>=5 통과 0건
    90일 창 → 노출>=5 통과 10건 (최다 노출 49)
같은 필터·같은 사이트인데 창 길이만 다르다. 28일은 저트래픽 블로그에서
모든 쿼리를 노출 5 미만으로 만들어 발굴을 0건으로 만든다.
"""
from __future__ import annotations

from src.application.use_cases.discover_keywords import (
    DEFAULT_LOOKBACK_DAYS,
    DiscoverKeywordsUseCase,
)
from src.domain.ports.keyword_port import KeywordResearchPort
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


class RecordingResearch(KeywordResearchPort):
    def __init__(self):
        self.calls: list[int] = []

    def fetch_queries(self, site_url: str, days: int = 28):
        self.calls.append(days)
        return []


class TestLookbackWindow:
    def test_기본_조회_기간은_90일(self):
        assert DEFAULT_LOOKBACK_DAYS == 90

    def test_execute_기본값이_90일로_조회(self):
        kr = RecordingResearch()
        uc = DiscoverKeywordsUseCase(repo=InMemoryPostRepository(), keyword_research=kr)
        uc.execute("https://example.com/")
        assert kr.calls == [90]

    def test_호출자가_기간을_덮어쓸_수_있다(self):
        kr = RecordingResearch()
        uc = DiscoverKeywordsUseCase(repo=InMemoryPostRepository(), keyword_research=kr)
        uc.execute("https://example.com/", days=28)
        assert kr.calls == [28]
