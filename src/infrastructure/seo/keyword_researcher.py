"""GscKeywordResearchAdapter — GSC Search Analytics API 기반 키워드 리서치."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from google.oauth2.service_account import Credentials as GoogleCredentials
from googleapiclient.discovery import build

from src.domain.ports.keyword_port import KeywordResearchPort
from src.domain.value_objects.keyword_suggestion import KeywordSuggestion

logger = logging.getLogger(__name__)

GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


class GscKeywordResearchAdapter(KeywordResearchPort):
    """Google Search Console Search Analytics API adapter."""

    def fetch_queries(
        self, site_url: str, days: int = 28,
    ) -> list[KeywordSuggestion]:
        creds_path = os.getenv("GOOGLE_CREDS", "")
        if not creds_path:
            raise RuntimeError("GOOGLE_CREDS 환경변수가 설정되지 않았습니다")

        creds = GoogleCredentials.from_service_account_file(
            creds_path, scopes=GSC_SCOPES,
        )
        service = build("searchconsole", "v1", credentials=creds)

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        response = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "dimensions": ["query"],
                "rowLimit": 500,
            },
        ).execute()

        rows = response.get("rows", [])
        suggestions = []
        for row in rows:
            keyword = row["keys"][0]
            impressions = int(row.get("impressions", 0))
            clicks = int(row.get("clicks", 0))
            ctr = float(row.get("ctr", 0.0))
            position = float(row.get("position", 0.0))
            opportunity = KeywordSuggestion.calculate_opportunity(impressions, ctr)

            suggestions.append(KeywordSuggestion(
                keyword=keyword,
                impressions=impressions,
                clicks=clicks,
                ctr=ctr,
                position=position,
                opportunity_score=opportunity,
            ))

        suggestions.sort(key=lambda x: x.opportunity_score, reverse=True)
        return suggestions
