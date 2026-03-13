"""CwvMeasurement — Value Object for Core Web Vitals measurement data."""
from __future__ import annotations

from dataclasses import dataclass


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
        if self.lcp_seconds <= 2.5:
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
        if self.cls_score <= 0.1:
            return "good"
        if self.cls_score <= 0.25:
            return "needs_improvement"
        return "poor"

    @property
    def needs_optimization(self) -> bool:
        """LCP 또는 CLS가 poor인 경우 최적화 필요."""
        return self.lcp_grade == "poor" or self.cls_grade == "poor"
