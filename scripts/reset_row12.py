"""Row 12 즉시 조치 — FAILED→PENDING 리셋 + error_msg 클리어.

1회성 스크립트. 실행 후 삭제 가능.
사용법: python3 scripts/reset_row12.py
"""
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

ROW = 12
STATUS_COL = 3    # C열: 상태
ERROR_COL = 13    # M열: 에러 메시지

creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
client = gspread.authorize(creds)
sheet = client.open("keyword_calendar_v2").sheet1

current_status = sheet.cell(ROW, STATUS_COL).value
print(f"Row {ROW} 현재 상태: {current_status}")

if current_status == "발행실패":
    sheet.update_cell(ROW, STATUS_COL, "발행대기")
    sheet.update_cell(ROW, ERROR_COL, "")
    print(f"Row {ROW} → 발행대기로 리셋 완료")
else:
    print(f"Row {ROW} 상태가 '발행실패'가 아님 ({current_status}) — 스킵")
