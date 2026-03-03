"""PageSpeed Insights API 연동 — Core Web Vitals 측정.

공개 REST API 사용 (API key 불요, rate limit 있음).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


@dataclass(frozen=True)
class CwvResult:
    """Core Web Vitals 측정 결과."""

    lcp_seconds: float = 0.0
    cls_score: float = 0.0
    performance_score: int = 0
    passed: bool = False
    error: str = ""


def check_cwv(url: str, strategy: str = "mobile") -> CwvResult:
    """Google PageSpeed Insights API로 CWV 측정.

    Args:
        url: 측정 대상 URL
        strategy: "mobile" | "desktop"

    Returns:
        CwvResult — 네트워크 오류 시 error 필드에 메시지 포함
    """
    try:
        resp = requests.get(
            PSI_URL,
            params={"url": url, "strategy": strategy},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning(f"PageSpeed API 호출 실패: {e}")
        return CwvResult(error=str(e))

    try:
        lighthouse = data["lighthouseResult"]
        audits = lighthouse["audits"]

        # LCP: milliseconds → seconds
        lcp_ms = audits["largest-contentful-paint"]["numericValue"]
        lcp_seconds = lcp_ms / 1000.0

        # CLS
        cls_score = audits["cumulative-layout-shift"]["numericValue"]

        # Performance score (0~1 → 0~100)
        perf_score = lighthouse["categories"]["performance"]["score"]
        performance_score = int(perf_score * 100)

        passed = lcp_seconds < 2.5

        return CwvResult(
            lcp_seconds=round(lcp_seconds, 2),
            cls_score=round(cls_score, 3),
            performance_score=performance_score,
            passed=passed,
        )
    except (KeyError, TypeError) as e:
        logger.warning(f"PageSpeed 응답 파싱 실패: {e}")
        return CwvResult(error=f"응답 파싱 실패: {e}")
