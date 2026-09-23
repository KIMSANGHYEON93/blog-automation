"""SheetsBrainTermAdapter — 시트 'AI브레인용어' 탭에서 용어 카드를 읽는다.

원본은 Drive 옵시디언 볼트이고 scripts/sync_brain_terms.py가 주 1회 이 탭을
갱신한다. n8n의 Route Prompt도 같은 탭을 읽으므로 스키마를 함께 지켜야 한다.
"""
from __future__ import annotations

import logging

import gspread
from google.oauth2.service_account import Credentials as GoogleCredentials
from gspread.http_client import BackOffHTTPClient

from src.domain.ports.brain_term_port import BrainTermPort
from src.domain.value_objects.brain_term import BrainTerm

logger = logging.getLogger(__name__)

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

WORKSHEET_NAME = "AI브레인용어"


def rows_to_terms(rows: list[dict]) -> list[BrainTerm]:
    """시트 레코드 → BrainTerm. 용어명이 빈 행은 버린다."""
    terms = []
    for r in rows:
        name = str(r.get("용어", "") or "").strip()
        if not name:
            continue
        terms.append(BrainTerm(
            name=name,
            definition=str(r.get("한줄정의", "") or ""),
            aliases_raw=str(r.get("별칭", "") or ""),
            confusion_raw=str(r.get("혼동포인트", "") or ""),
            source=str(r.get("출처", "") or ""),
        ))
    return terms


class SheetsBrainTermAdapter(BrainTermPort):
    def __init__(self, creds_path: str, sheet_name: str,
                 worksheet_name: str = WORKSHEET_NAME):
        self._creds_path = creds_path
        self._sheet_name = sheet_name
        self._worksheet_name = worksheet_name

    def fetch_terms(self) -> list[BrainTerm]:
        creds = GoogleCredentials.from_service_account_file(
            self._creds_path, scopes=SCOPES,
        )
        client = gspread.authorize(creds, http_client=BackOffHTTPClient)
        ws = client.open(self._sheet_name).worksheet(self._worksheet_name)
        terms = rows_to_terms(ws.get_all_records())
        logger.info(f"볼트 용어 조회: {len(terms)}건 ({self._worksheet_name} 탭)")
        return terms
