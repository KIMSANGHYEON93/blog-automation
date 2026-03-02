#!/bin/bash
# Pipeline A 최근 실행 결과 상세 확인
# 사용법: ./check_last_run.sh
# 아침에 실행하면 01:00 AM 자동 실행 결과를 확인할 수 있음

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
N8N_API_KEY_FILE="/tmp/n8n_api_key.txt"

# API 키 로드 (fallback chain: 파일 → .env → 환경변수)
_load_n8n_api_key() {
    if [ -f "$N8N_API_KEY_FILE" ]; then
        cat "$N8N_API_KEY_FILE"
    elif [ -f "${PROJECT_DIR}/.env" ] && grep -q '^N8N_API_KEY=' "${PROJECT_DIR}/.env"; then
        grep '^N8N_API_KEY=' "${PROJECT_DIR}/.env" | cut -d'=' -f2-
    elif [ -n "${N8N_API_KEY:-}" ]; then
        echo "$N8N_API_KEY"
    else
        echo ""
    fi
}
API_KEY=$(_load_n8n_api_key)

if [ -z "$API_KEY" ]; then
    echo "ERROR: API 키 없음 (파일/환경변수/.env 모두 미설정)"
    echo "  → ./setup_n8n_apikey.sh 실행 또는 .env에 N8N_API_KEY 설정"
    exit 1
fi

echo "=== Pipeline A — 최근 실행 상세 ==="
echo

curl -s "http://localhost:5678/api/v1/executions?limit=3" -H "X-N8N-API-KEY: $API_KEY" 2>/dev/null | python3 -c "
import sys, json

data = json.load(sys.stdin)
execs = data.get('data', [])

for e in execs:
    eid = e.get('id', '?')
    mode = e.get('mode', '?')
    finished = e.get('finished', False)
    started = e.get('startedAt', '?')[:19].replace('T', ' ')
    stopped = e.get('stoppedAt', '')
    if stopped:
        stopped = stopped[:19].replace('T', ' ')

    status = '성공' if finished else '실패'
    mode_kr = {'trigger': '자동(스케줄)', 'manual': '수동', 'cli': 'CLI'}.get(mode, mode)

    # Calculate duration
    duration = ''
    if e.get('startedAt') and e.get('stoppedAt'):
        from datetime import datetime
        start_dt = datetime.fromisoformat(e['startedAt'].replace('Z', '+00:00'))
        stop_dt = datetime.fromisoformat(e['stoppedAt'].replace('Z', '+00:00'))
        dur = (stop_dt - start_dt).total_seconds()
        if dur >= 60:
            duration = f'{int(dur//60)}분 {int(dur%60)}초'
        else:
            duration = f'{dur:.1f}초'

    print(f'실행 #{eid}')
    print(f'  상태: {status}')
    print(f'  모드: {mode_kr}')
    print(f'  시작: {started}')
    print(f'  종료: {stopped}')
    print(f'  소요: {duration}')
    print()
" 2>/dev/null

echo "=== Google Sheets 변동 확인 ==="
python3 -c "
import gspread
from google.oauth2.service_account import Credentials
from collections import Counter

creds = Credentials.from_service_account_file('${PROJECT_DIR}/credentials.json', scopes=[
    'https://www.googleapis.com/auth/spreadsheets'
])
gc = gspread.authorize(creds)
sh = gc.open_by_key('1VbyEQNuIAKpmTfk_5pTIjuLb3xlS-kdUfWflmfnFJSA')
ws = sh.worksheet('시트1')
rows = ws.get_all_records()

statuses = Counter(row.get('상태', '') or '(빈칸)' for row in rows)
print(f'  대기: {statuses.get(\"대기\", 0)} | 발행대기: {statuses.get(\"발행대기\", 0)} | 발행완료: {statuses.get(\"발행완료\", 0)} | 검수필요: {statuses.get(\"검수필요\", 0)}')
print()

# Show recently generated items (by 생성일시)
recent = [(i+2, row) for i, row in enumerate(rows) if row.get('생성일시')]
recent.sort(key=lambda x: x[1].get('생성일시', ''), reverse=True)
print('최근 생성된 콘텐츠:')
for row_num, row in recent[:5]:
    kw = row.get('키워드', '')
    status = row.get('상태', '')
    created = row.get('생성일시', '')
    content_len = len(str(row.get('본문마크다운', '')))
    print(f'  Row {row_num}: {kw} [{status}] {content_len}자 ({created})')
" 2>/dev/null || echo "  Sheets 조회 실패"
