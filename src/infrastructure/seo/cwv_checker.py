"""PageSpeed Insights API 연동 — Core Web Vitals 측정.

API key 설정 시 하루 25,000건, 미설정 시 ~25건 제한.
환경변수: PAGESPEED_API_KEY
"""
from __future__ import annotations

import logging
import os
from dataclasses import replace

import requests

from src.domain.ports.seo_port import CwvPort, CwvResult
from src.domain.value_objects.cwv_measurement import meets_cwv_thresholds

logger = logging.getLogger(__name__)

PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


class PageSpeedCwvAdapter(CwvPort):
    """Google PageSpeed Insights API adapter.

    모바일과 데스크톱을 함께 잰다. 티스토리는 모바일 접속을 `/m/` 모바일 웹으로 넘겨
    플랫폼 리소스(2MB 글꼴 등)가 모바일 점수를 좌우하므로, 데스크톱 값이 있어야
    글·스킨 문제와 플랫폼 문제를 가를 수 있다(2026-10-28 실측: 모바일 LCP 5.3s / 데스크톱 1.8s).
    """

    def check(self, url: str) -> CwvResult:
        """모바일 측정이 기준값(시트 기록·판정)이고, 데스크톱은 비교용으로 덧붙인다.

        Returns:
            CwvResult — 모바일 측정 실패 시 error 필드에 메시지 포함. 데스크톱 실패는
            모바일 결과를 버리지 않고 desktop=None으로 남긴다.
        """
        mobile = self._measure(url, "mobile")
        if mobile.error:
            return mobile
        desktop = self._measure(url, "desktop")
        if desktop.error:
            logger.warning(f"데스크톱 CWV 측정 실패 — 모바일 결과만 기록: {desktop.error}")
            return mobile
        return replace(mobile, desktop=desktop)

    def _measure(self, url: str, strategy: str) -> CwvResult:
        try:
            params: dict[str, str] = {"url": url, "strategy": strategy}
            api_key = os.getenv("PAGESPEED_API_KEY", "")
            if api_key:
                params["key"] = api_key
            resp = requests.get(PSI_URL, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.warning(f"PageSpeed API 호출 실패({strategy}): {e}")
            return CwvResult(error=str(e))

        try:
            lighthouse = data["lighthouseResult"]
            audits = lighthouse["audits"]

            # LCP: milliseconds → seconds
            lcp_seconds = audits["largest-contentful-paint"]["numericValue"] / 1000.0
            cls_score = audits["cumulative-layout-shift"]["numericValue"]

            # Performance score (0~1 → 0~100)
            performance_score = int(lighthouse["categories"]["performance"]["score"] * 100)

            # CrUX 실사용자 평가 — 트래픽이 적은 URL은 없다
            field_category = (data.get("loadingExperience") or {}).get("overall_category", "")

            return CwvResult(
                lcp_seconds=round(lcp_seconds, 2),
                cls_score=round(cls_score, 3),
                performance_score=performance_score,
                passed=meets_cwv_thresholds(lcp_seconds, cls_score),
                field_category=field_category,
            )
        except (KeyError, TypeError) as e:
            logger.warning(f"PageSpeed 응답 파싱 실패({strategy}): {e}")
            return CwvResult(error=f"응답 파싱 실패: {e}")
