"""DiscoverKeywordsUseCase — GSC 데이터 기반 키워드 자동 발굴."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from src.domain.ports.keyword_port import KeywordResearchPort
from src.domain.ports.post_repository import PostRepository
from src.domain.services.keyword_matcher import find_duplicate, is_covered_by_existing
from src.domain.value_objects.keyword_suggestion import KeywordSuggestion

logger = logging.getLogger(__name__)


@dataclass
class KeywordDiscoveryResult:
    """키워드 발굴 결과 DTO."""

    success: bool
    suggestions: list[KeywordSuggestion]
    total_queries: int = 0
    filtered: int = 0
    registered: int = 0
    error: str = ""


B2C_BLOCKLIST: set[str] = {
    "우회", "무료", "할인", "쿠폰", "공짜", "크랙", "프리미엄",
    "유튜브", "넷플릭스", "아이폰", "갤럭시", "게임", "다운로드",
    "토렌트", "vpn 우회", "upi", "인도 우회", "인도 아마존", "구글 플레이",
    "앱스토어", "환불", "해지", "결제", "구독", "꿀팁",
    "미역국", "레시피", "맛집", "요리", "회원가입 안됨", "가입 안됨",
    "아마존 인도",
    # 해외 스토어 결제/배송 문의 유입 (2026-09-21 자동 등록된 잡음)
    "애플 인도", "인도 계정", "payment method required", "invalid address",
    "purchase could not be completed", "your purchase", "billing address",
    "나무위키",
    # 소비자 결제 수단 (B2B 인프라와 무관)
    "기프트카드", "상품권", "애플페이", "삼성페이", "페이코", "카카오페이",
    "포인트 충전", "충전 방법",
}

# n8n check_duplicate.js와 같은 값 — 등록 단계에서 미리 같은 기준으로 거른다
DUPLICATE_THRESHOLD = 0.7

# '인도 payment' 처럼 단어 단위로만 막을 패턴 (인도네시아 등 정상 키워드 보호)
B2C_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:^|\s)인도(?:\s|$)"),
)


def is_b2c_noise(keyword: str, blocked: set[str]) -> bool:
    """B2B IT 블로그와 무관한 B2C 검색어인지 판정."""
    kw = keyword.lower().strip()
    if any(term in kw for term in blocked):
        return True
    return any(pattern.search(kw) for pattern in B2C_TOKEN_PATTERNS)


# GSC 조회 기간. 28일 창은 저트래픽 블로그에서 쿼리별 노출이 흩어져
# min_impressions 임계치를 아무도 넘지 못한다 — 2026-09-23 실측으로
# 28일 통과 0건 / 90일 통과 10건(최다 노출 49). 창을 넓혀 누적 노출로 본다.
DEFAULT_LOOKBACK_DAYS = 90


class DiscoverKeywordsUseCase:
    """GSC 검색 데이터에서 키워드를 발굴하여 제안.

    필터링 전략:
    - impressions >= min_impressions (기본 5)
    - position < max_position (기본 30)
    - ctr < max_ctr (기본 0.10 = 10%)
    - B2C 차단 키워드 제외
    - 기존 키워드 중복 제외
    - opportunity_score = impressions × (1 - ctr) 내림차순 Top N
    """

    def __init__(
        self,
        repo: PostRepository,
        keyword_research: KeywordResearchPort,
        min_impressions: int = 5,
        max_position: float = 30.0,
        max_ctr: float = 0.10,
        top_n: int = 10,
        blocked_keywords: set[str] | None = None,
    ):
        self._repo = repo
        self._keyword_research = keyword_research
        self._min_impressions = min_impressions
        self._max_position = max_position
        self._max_ctr = max_ctr
        self._top_n = top_n
        self._blocked = blocked_keywords if blocked_keywords is not None else B2C_BLOCKLIST

    def execute(
        self, site_url: str, days: int = DEFAULT_LOOKBACK_DAYS,
        auto_register: bool = False,
    ) -> KeywordDiscoveryResult:
        try:
            queries = self._keyword_research.fetch_queries(site_url, days=days)
        except Exception as e:
            logger.error(f"GSC 검색 데이터 조회 실패: {e}")
            return KeywordDiscoveryResult(
                success=False, suggestions=[], error=str(e)[:200],
            )

        if not queries:
            return KeywordDiscoveryResult(success=True, suggestions=[])

        # 기존 키워드 수집 (중복 제외용)
        all_posts = self._repo.find_all()
        existing_keywords = [p.keyword for p in all_posts if p.keyword]

        # 필터링 (게이트별 탈락 카운트)
        filtered = []
        gate_impressions = gate_position = gate_ctr = gate_existing = gate_b2c = 0
        for q in queries:
            if q.impressions < self._min_impressions:
                gate_impressions += 1
                continue
            if q.position >= self._max_position:
                gate_position += 1
                continue
            if q.ctr >= self._max_ctr:
                gate_ctr += 1
                continue
            kw_lower = q.keyword.lower().strip()
            # Pipeline A와 같은 기준(토큰 겹침 70%)으로 유사 중복까지 제외 —
            # 등록해도 n8n이 중복스킵 처리하므로 자리만 낭비됨
            is_dup, _, _ = find_duplicate(q.keyword, existing_keywords, DUPLICATE_THRESHOLD)
            if is_dup or is_covered_by_existing(q.keyword, existing_keywords):
                gate_existing += 1
                continue
            if is_b2c_noise(kw_lower, self._blocked):
                gate_b2c += 1
                continue
            filtered.append(q)

        logger.info(
            f"필터 상세: 노출<{self._min_impressions}={gate_impressions}, "
            f"순위>={self._max_position}={gate_position}, "
            f"CTR>={self._max_ctr}={gate_ctr}, "
            f"기존키워드={gate_existing}, "
            f"B2C차단={gate_b2c}"
        )

        # opportunity_score 내림차순 정렬 → Top N
        filtered.sort(key=lambda x: x.opportunity_score, reverse=True)
        suggestions = filtered[: self._top_n]

        logger.info(
            f"키워드 발굴: 전체 {len(queries)}건 → "
            f"필터링 {len(filtered)}건 → 제안 {len(suggestions)}건"
        )

        registered = 0
        if auto_register and suggestions:
            for s in suggestions:
                try:
                    self._repo.add_keyword_row(s.keyword)
                    registered += 1
                except Exception as e:
                    logger.warning(f"키워드 등록 실패: {s.keyword} — {e}")

            logger.info(f"시트 자동 등록: {registered}/{len(suggestions)}건")

        return KeywordDiscoveryResult(
            success=True,
            suggestions=suggestions,
            total_queries=len(queries),
            filtered=len(filtered),
            registered=registered,
        )
