"""CwvMeasurement — Value Object for Core Web Vitals measurement data."""
from __future__ import annotations

from dataclasses import dataclass

# Google 'good' 기준
LCP_GOOD_SECONDS = 2.5
CLS_GOOD = 0.1


def meets_cwv_thresholds(lcp_seconds: float, cls_score: float) -> bool:
    """LCP와 CLS가 둘 다 good이어야 통과. LCP만 보면 본문이 통째로 밀리는 글을 놓친다."""
    return lcp_seconds <= LCP_GOOD_SECONDS and cls_score <= CLS_GOOD


@dataclass(frozen=True)
class CwvMeasurement:
    """CWV 측정값 도메인 모델. 시트에 직접 기록하는 대신 도메인 로직으로 평가."""

    lcp_seconds: float
    cls_score: float
    performance_score: int
    passed: bool

    @property
    def lcp_grade(self) -> str:
        """LCP 등급 판정 (Google 기준).

        - good: ≤ 2.5s
        - needs_improvement: ≤ 4.0s
        - poor: > 4.0s
        """
        if self.lcp_seconds <= LCP_GOOD_SECONDS:
            return "good"
        if self.lcp_seconds <= 4.0:
            return "needs_improvement"
        return "poor"

    @property
    def cls_grade(self) -> str:
        """CLS 등급 판정 (Google 기준).

        - good: ≤ 0.1
        - needs_improvement: ≤ 0.25
        - poor: > 0.25
        """
        if self.cls_score <= CLS_GOOD:
            return "good"
        if self.cls_score <= 0.25:
            return "needs_improvement"
        return "poor"

    @property
    def needs_optimization(self) -> bool:
        """LCP 또는 CLS가 poor인 경우 최적화 필요."""
        return self.lcp_grade == "poor" or self.cls_grade == "poor"
