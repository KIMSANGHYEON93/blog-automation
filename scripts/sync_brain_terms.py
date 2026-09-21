"""AI-Brain 볼트(Google Drive) 용어 카드 → 시트 `AI브레인용어` 탭 동기화.

Pipeline A의 Route Prompt가 이 탭을 읽어 키워드와 매칭되는 용어 정의를
생성 프롬프트에 주입한다(CLAUDE.md 참고).

사용법:
    python scripts/sync_brain_terms.py --dry-run   # 미리보기
    python scripts/sync_brain_terms.py             # 시트 갱신

전제: 서비스 계정(credentials.json)에 볼트 폴더가 읽기 권한으로 공유돼 있어야 한다.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

load_dotenv()

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
TAB_NAME = "AI브레인용어"
HEADER = ["용어", "별칭", "한줄정의", "혼동포인트", "출처"]
TERMS_FOLDER_NAME = "10_Terms"
# 출처 칸이 채워지지 않은 카드의 플레이스홀더
SOURCE_PLACEHOLDERS = ("공식 문서", "논문 링크", "추가)")
MAX_FIELD_CHARS = 400


@dataclass(frozen=True)
class BrainTerm:
    name: str
    aliases: str
    definition: str
    confusion: str
    source: str

    def to_row(self) -> list[str]:
        return [self.name, self.aliases, self.definition, self.confusion, self.source]


def _unescape(text: str) -> str:
    r"""Drive 내보내기가 넣는 백슬래시 이스케이프(\#, \---, \[)를 제거."""
    return re.sub(r"\\([#\-\[\]*_`>|])", r"\1", text)


def _clean(value: str) -> str:
    value = value.replace("**", "")
    return re.sub(r"\s+", " ", value).strip()[:MAX_FIELD_CHARS]


def _first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    return _clean(match.group(1)) if match else ""


def parse_term_card(raw: str, filename: str) -> BrainTerm | None:
    """용어 카드 마크다운에서 시트 행에 넣을 필드 추출. 한 줄 정의가 없으면 None."""
    text = _unescape(raw)
    definition = _first_match(r"한 줄 정의:\*{0,2}\s*(.+?)(?:\n|$)", text)
    if not definition:
        return None

    name = _first_match(r'^\s*title:\s*"?([^"\n]+)"?', text) or filename.rsplit(".", 1)[0]
    raw_aliases = _first_match(r"^\s*aliases:\s*\[(.*?)\]", text)
    alias_list = [a.strip().strip("\"'") for a in raw_aliases.split(",")]
    aliases = ", ".join(dict.fromkeys(a for a in alias_list if a))
    confusion = _first_match(r"혼동 포인트:\*{0,2}\s*(.+?)(?:\n|$)", text)
    source = _first_match(r"원문:\s*\[([^\]]+)\]", text)
    if any(p in source for p in SOURCE_PLACEHOLDERS):
        source = ""
    return BrainTerm(name=name, aliases=aliases, definition=definition,
                     confusion=confusion, source=source)


def fetch_term_cards(drive, vault_folder_id: str) -> list[tuple[str, str]]:
    """볼트의 10_Terms 폴더에서 (파일명, 본문) 목록을 가져온다."""
    folders = drive.files().list(
        q=f"'{vault_folder_id}' in parents and name = '{TERMS_FOLDER_NAME}' and trashed = false",
        fields="files(id)",
    ).execute().get("files", [])
    if not folders:
        raise SystemExit(f"{TERMS_FOLDER_NAME} 폴더를 찾을 수 없음 (볼트 공유 여부 확인)")

    cards: list[tuple[str, str]] = []
    page_token = None
    while True:
        res = drive.files().list(
            q=f"'{folders[0]['id']}' in parents and trashed = false",
            fields="nextPageToken, files(id, name)", pageSize=200, pageToken=page_token,
        ).execute()
        for f in res.get("files", []):
            if not f["name"].endswith(".md"):
                continue
            content = drive.files().get_media(fileId=f["id"]).execute()
            cards.append((f["name"], content.decode("utf-8", "ignore")))
        page_token = res.get("nextPageToken")
        if not page_token:
            return cards


def write_terms(spreadsheet, terms: list[BrainTerm]) -> None:
    try:
        ws = spreadsheet.worksheet(TAB_NAME)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(
            title=TAB_NAME, rows=max(len(terms) + 10, 100), cols=len(HEADER),
        )
    ws.clear()
    ws.update(values=[HEADER] + [t.to_row() for t in terms], range_name="A1")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI-Brain 용어 → 시트 동기화")
    parser.add_argument("--dry-run", action="store_true", help="시트 변경 없이 결과만 출력")
    parser.add_argument("--vault-folder-id", default=os.getenv("BRAIN_VAULT_FOLDER_ID", ""),
                        help="볼트 루트 폴더 ID (.env의 BRAIN_VAULT_FOLDER_ID)")
    args = parser.parse_args()
    if not args.vault_folder_id:
        print("BRAIN_VAULT_FOLDER_ID 미설정 (.env 또는 --vault-folder-id)", file=sys.stderr)
        return 2

    creds = Credentials.from_service_account_file(
        os.getenv("GOOGLE_CREDS", "credentials.json"), scopes=SCOPES,
    )
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    cards = fetch_term_cards(drive, args.vault_folder_id)

    terms: list[BrainTerm] = []
    skipped: list[str] = []
    for filename, raw in cards:
        term = parse_term_card(raw, filename)
        if term:
            terms.append(term)
        else:
            skipped.append(filename)
    terms.sort(key=lambda t: t.name)

    print(f"카드 {len(cards)}건 → 용어 {len(terms)}건 (정의 없음 {len(skipped)}건)")
    for t in terms[:5]:
        print(f"  {t.name} | {t.definition[:60]}")
    if skipped[:5]:
        print("  건너뜀:", ", ".join(skipped[:5]))
    if args.dry_run:
        print("--dry-run: 시트 변경 없음")
        return 0

    spreadsheet = gspread.authorize(creds).open(os.getenv("SHEET_NAME", "keyword_calendar_v2"))
    write_terms(spreadsheet, terms)
    print(f"'{TAB_NAME}' 탭 갱신 완료: {len(terms)}행")
    return 0


if __name__ == "__main__":
    sys.exit(main())
