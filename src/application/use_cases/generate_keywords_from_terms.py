"""GenerateKeywordsFromTermsUseCase — 볼트 용어에서 키워드를 역방향 생성.

GSC 발굴(DiscoverKeywordsUseCase)은 '이미 노출된 쿼리'만 돌려주므로
트래픽 없음 → 키워드 없음 → 글 없음 → 트래픽 없음 루프에 갇힌다.
볼트 용어는 트래픽과 무관한 시드라 이 루프를 끊는다.

중복·B2C 필터는 GSC 발굴과 같은 것을 쓴다 — 기준이 갈리면 한쪽이 등록한
키워드를 Pipeline A가 중복으로 버려 자리만 낭비한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.application.use_cases.discover_keywords import (
    B2C_BLOCKLIST,
    DUPLICATE_THRESHOLD,
    is_b2c_noise,
)
from src.domain.ports.brain_term_port import BrainTermPort
from src.domain.ports.post_repository import PostRepository
from src.domain.services.keyword_matcher import find_duplicate, is_covered_by_existing
from src.domain.value_objects.keyword_suggestion import KeywordSuggestion

logger = logging.getLogger(__name__)

DEFAULT_TOP_N = 10


@dataclass
class TermKeywordResult:
    success: bool
    suggestions: list[KeywordSuggestion] = field(default_factory=list)
    total_terms: int = 0
    generated: int = 0
    registered: int = 0
    error: str = ""


class GenerateKeywordsFromTermsUseCase:
    def __init__(
        self,
        repo: PostRepository,
        term_port: BrainTermPort,
        top_n: int = DEFAULT_TOP_N,
        blocked_keywords: set[str] | None = None,
    ):
        self._repo = repo
        self._term_port = term_port
        self._top_n = top_n
        self._blocked = blocked_keywords if blocked_keywords is not None else B2C_BLOCKLIST

    def execute(self, auto_register: bool = False) -> TermKeywordResult:
        try:
            terms = self._term_port.fetch_terms()
        except Exception as e:
            logger.error(f"볼트 용어 조회 실패: {e}")
            return TermKeywordResult(success=False, error=str(e)[:200])

        if not terms:
            logger.info("볼트 용어 없음")
            return TermKeywordResult(success=True)

        existing = [p.keyword for p in self._repo.find_all() if p.keyword]

        # 볼트는 가나다순이라 마이너 용어가 앞에 온다. 검색 수요 대용 지표로
        # 다시 세워야 top_n이 의미 있는 상위를 자른다.
        terms = sorted(terms, key=lambda t: (-t.priority(), t.name))

        kept: list[str] = []
        gate_dup = gate_b2c = 0
        for t in terms:
            for kw in t.keyword_candidates():
                if kw in kept:
                    continue
                if is_b2c_noise(kw.lower().strip(), self._blocked):
                    gate_b2c += 1
                    continue
                # 이미 등록한 후보도 중복 판정에 넣어야 같은 배치 안에서 유사
                # 키워드가 둘 다 통과하는 일이 없다.
                pool = existing + kept
                is_dup, _, _ = find_duplicate(kw, pool, DUPLICATE_THRESHOLD)
                if is_dup or is_covered_by_existing(kw, pool):
                    gate_dup += 1
                    continue
                kept.append(kw)

        logger.info(
            f"용어 키워드 생성: 용어 {len(terms)}건 → 후보 {len(kept)}건 "
            f"(중복 제외 {gate_dup}, B2C 제외 {gate_b2c})"
        )

        suggestions = [KeywordSuggestion(keyword=k) for k in kept[: self._top_n]]
        registered = 0
        if auto_register:
            registered = self._register(suggestions)

        return TermKeywordResult(
            success=True,
            suggestions=suggestions,
            total_terms=len(terms),
            generated=len(kept),
            registered=registered,
        )

    def _register(self, suggestions: list[KeywordSuggestion]) -> int:
        """시트에 '대기' 상태로 등록. 한 건 실패가 전체를 막지 않는다."""
        count = 0
        for s in suggestions:
            try:
                row = self._repo.add_keyword_row(s.keyword)
                count += 1
                logger.info(f"용어 키워드 등록: row={row}, keyword={s.keyword}")
            except Exception as e:
                logger.warning(f"키워드 등록 실패: {s.keyword} — {e}")
        logger.info(f"시트 자동 등록: {count}/{len(suggestions)}건")
        return count
