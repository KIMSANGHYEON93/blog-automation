"""KeywordMatcher — 키워드 유사도 비교 (중복 감지용).

Domain Service: stdlib만 사용, 외부 의존성 없음.
"""
from __future__ import annotations


def keyword_overlap(kw_a: str, kw_b: str) -> float:
    """두 키워드의 토큰 중복도 계산 (0.0 ~ 1.0).

    토큰이 1개 이하인 경우 정확 일치만 판정.
    """
    tokens_a = set(kw_a.lower().split())
    tokens_b = set(kw_b.lower().split())

    # 단일 토큰 키워드: 정확 일치만 비교
    if len(tokens_a) < 2 or len(tokens_b) < 2:
        return 1.0 if kw_a.lower().strip() == kw_b.lower().strip() else 0.0

    intersection = tokens_a & tokens_b
    smaller = min(len(tokens_a), len(tokens_b))
    return len(intersection) / smaller if smaller > 0 else 0.0


def find_duplicate(
    keyword: str,
    existing_keywords: list[str],
    threshold: float = 0.7,
) -> tuple[bool, str, float]:
    """키워드가 기존 목록과 중복인지 판정.

    Returns:
        (is_duplicate, matched_keyword, overlap_score)
    """
    kw_lower = keyword.lower().strip()
    best_match = ""
    best_score = 0.0

    for existing in existing_keywords:
        ex_lower = existing.lower().strip()

        # 정확 일치
        if kw_lower == ex_lower:
            return True, existing, 1.0

        # 토큰 유사도
        score = keyword_overlap(kw_lower, ex_lower)
        if score > best_score:
            best_score = score
            best_match = existing

        if score >= threshold:
            return True, existing, score

    return False, best_match, best_score
