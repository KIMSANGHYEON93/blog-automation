"""Google Search Console URL Inspection API — 색인 상태 확인.

서비스 계정에 Search Console 속성 접근 권한이 있어야 함.
환경변수: GOOGLE_CREDS (서비스 계정 JSON 키 경로)
"""
from __future__ import annotations

import logging
import os

from google.oauth2.service_account import Credentials as GoogleCredentials
from googleapiclient.discovery import build

from src.domain.ports.seo_port import IndexingPort, IndexingResult

logger = logging.getLogger(__name__)

GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


class GscIndexingAdapter(IndexingPort):
    """Google Search Console URL Inspection API adapter."""

    def check(self, url: str, site_url: str = "") -> IndexingResult:
        """Google Search Console URL Inspection API로 색인 상태 확인.

        Args:
            url: 검사 대상 URL
            site_url: Search Console 속성 URL (e.g. "https://kimsanghyeon.tistory.com/")
                      미지정 시 환경변수 TISTORY_BLOG에서 추출

        Returns:
            IndexingResult — API 오류 시 error 필드에 메시지 포함
        """
        creds_path = os.getenv("GOOGLE_CREDS", "")
        if not creds_path:
            return IndexingResult(url=url, error="GOOGLE_CREDS 환경변수가 설정되지 않았습니다")

        if not site_url:
            blog_name = os.getenv("TISTORY_BLOG", "")
            if not blog_name:
                return IndexingResult(url=url, error="TISTORY_BLOG 환경변수가 설정되지 않았습니다")
            site_url = f"https://{blog_name}.tistory.com/"

        try:
            creds = GoogleCredentials.from_service_account_file(
                creds_path, scopes=GSC_SCOPES,
            )
            service = build("searchconsole", "v1", credentials=creds)

            result = service.urlInspection().index().inspect(
                body={
                    "inspectionUrl": url,
                    "siteUrl": site_url,
                },
            ).execute()
        except Exception as e:
            logger.warning(f"GSC URL Inspection API 호출 실패: {e}")
            return IndexingResult(url=url, error=str(e)[:200])

        try:
            inspection = result.get("inspectionResult", {})
            index_status = inspection.get("indexStatusResult", {})

            verdict = index_status.get("verdict", "")
            coverage_state = index_status.get("coverageState", "")
            indexing_state = index_status.get("indexingState", "")
            robots_txt_state = index_status.get("robotsTxtState", "")
            last_crawl = index_status.get("lastCrawlTime", "")

            is_indexed = verdict == "PASS"

            return IndexingResult(
                url=url,
                is_indexed=is_indexed,
                verdict=verdict,
                coverage_state=coverage_state,
                indexing_state=indexing_state,
                robots_txt_state=robots_txt_state,
                last_crawl_time=last_crawl,
            )
        except (KeyError, TypeError) as e:
            logger.warning(f"GSC 응답 파싱 실패: {e}")
            return IndexingResult(url=url, error=f"응답 파싱 실패: {e}")
