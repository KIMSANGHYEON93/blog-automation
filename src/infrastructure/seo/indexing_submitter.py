"""Google Indexing API — 발행 후 즉시 크롤링 요청.

서비스 계정에 Search Console 소유자 권한이 있어야 함.
환경변수: GOOGLE_CREDS (서비스 계정 JSON 키 경로)
"""
from __future__ import annotations

import logging
import os

from google.oauth2.service_account import Credentials as GoogleCredentials
from googleapiclient.discovery import build

from src.domain.ports.seo_port import IndexingSubmitPort, IndexingSubmitResult

logger = logging.getLogger(__name__)

INDEXING_SCOPES = ["https://www.googleapis.com/auth/indexing"]


class GscIndexingSubmitAdapter(IndexingSubmitPort):
    """Google Indexing API adapter — URL_UPDATED 알림 전송."""

    def submit(self, url: str) -> IndexingSubmitResult:
        creds_path = os.getenv("GOOGLE_CREDS", "")
        if not creds_path:
            return IndexingSubmitResult(
                url=url, error="GOOGLE_CREDS 환경변수가 설정되지 않았습니다",
            )

        try:
            creds = GoogleCredentials.from_service_account_file(
                creds_path, scopes=INDEXING_SCOPES,
            )
            service = build("indexing", "v3", credentials=creds)

            service.urlNotifications().publish(
                body={
                    "url": url,
                    "type": "URL_UPDATED",
                },
            ).execute()

            return IndexingSubmitResult(url=url, success=True)

        except Exception as e:
            logger.warning(f"Indexing API 호출 실패: {e}")
            return IndexingSubmitResult(url=url, error=str(e)[:200])
