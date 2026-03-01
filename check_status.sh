#!/bin/bash
# 파이프라인 상태 모니터링 스크립트
# 사용법: ./check_status.sh [--detail]
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
N8N_API_KEY_FILE="/tmp/n8n_api_key.txt"
DETAIL="${1:-}"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Blog Automation — 파이프라인 상태 점검${NC}"
echo -e "${CYAN}  $(date '+%Y-%m-%d %H:%M:%S %Z')${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo

# === 1. Docker / n8n 상태 ===
echo -e "${YELLOW}[1] Docker & n8n 상태${NC}"
if docker ps --filter "name=blog-automation-n8n" --format "{{.Names}}" 2>/dev/null | grep -q "n8n"; then
    UPTIME=$(docker ps --filter "name=blog-automation-n8n" --format "{{.Status}}" 2>/dev/null)
    echo -e "  n8n 컨테이너: ${GREEN}실행중${NC} ($UPTIME)"
else
    echo -e "  n8n 컨테이너: ${RED}중지됨${NC}"
    echo -e "  ${RED}→ docker compose up -d 실행 필요${NC}"
fi
echo

# === 2. 워크플로우 상태 ===
echo -e "${YELLOW}[2] n8n 워크플로우 상태${NC}"
if [ -f "$N8N_API_KEY_FILE" ]; then
    API_KEY=$(cat "$N8N_API_KEY_FILE")
    WORKFLOWS=$(curl -s "http://localhost:5678/api/v1/workflows" -H "X-N8N-API-KEY: $API_KEY" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$WORKFLOWS" ]; then
        echo "$WORKFLOWS" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for w in data.get('data', []):
        status = '✅ 활성' if w['active'] else '⏸  비활성'
        print(f'  {w[\"name\"]}: {status}')
except:
    print('  API 응답 파싱 실패')
" 2>/dev/null
    else
        echo -e "  ${RED}n8n API 연결 실패${NC}"
    fi
else
    echo -e "  ${RED}API 키 파일 없음 ($N8N_API_KEY_FILE)${NC}"
fi
echo

# === 3. 최근 Pipeline A 실행 이력 ===
echo -e "${YELLOW}[3] Pipeline A — 최근 실행 이력 (n8n)${NC}"
if [ -f "$N8N_API_KEY_FILE" ]; then
    API_KEY=$(cat "$N8N_API_KEY_FILE")
    curl -s "http://localhost:5678/api/v1/executions?limit=5" -H "X-N8N-API-KEY: $API_KEY" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    execs = data.get('data', [])
    if not execs:
        print('  실행 이력 없음')
    for e in execs:
        eid = e.get('id', '?')
        mode = e.get('mode', '?')
        finished = e.get('finished', False)
        started = e.get('startedAt', '?')[:19].replace('T', ' ')
        stopped = e.get('stoppedAt', '?')
        if stopped:
            stopped = stopped[:19].replace('T', ' ')
        status = '✅ 성공' if finished else '❌ 실패'
        mode_kr = {'trigger': '자동(스케줄)', 'manual': '수동', 'cli': 'CLI'}.get(mode, mode)
        print(f'  #{eid} {status} | {mode_kr:12s} | {started}')
except:
    print('  실행 이력 조회 실패')
" 2>/dev/null
fi
echo

# === 4. Pipeline B 최근 로그 ===
echo -e "${YELLOW}[4] Pipeline B — 최근 실행 로그${NC}"
LOG_DIR="${PROJECT_DIR}/logs"
if [ -d "$LOG_DIR" ]; then
    LATEST_LOG=$(ls -t "$LOG_DIR"/pipeline_b_*.log 2>/dev/null | head -1 || true)
    if [ -n "${LATEST_LOG:-}" ]; then
        echo "  최신 로그: $(basename "$LATEST_LOG")"
        # 마지막 5줄 표시
        tail -5 "$LATEST_LOG" | while IFS= read -r line; do
            echo "  $line"
        done
    else
        echo "  로그 파일 없음 (Pipeline B 미실행)"
    fi
else
    echo -e "  ${RED}logs/ 디렉토리 없음${NC}"
fi
echo

# === 5. Crontab 상태 ===
echo -e "${YELLOW}[5] Crontab (Pipeline B 스케줄)${NC}"
CRON=$(crontab -l 2>/dev/null | grep -v "^#" | grep "pipeline_b" || true)
if [ -n "$CRON" ]; then
    echo -e "  ${GREEN}등록됨${NC}: $CRON"
else
    echo -e "  ${RED}Pipeline B crontab 미등록${NC}"
fi
echo

# === 6. Google Sheets 현황 ===
echo -e "${YELLOW}[6] Google Sheets — 키워드 상태 현황${NC}"
python3 -c "
import gspread
from google.oauth2.service_account import Credentials

creds = Credentials.from_service_account_file('${PROJECT_DIR}/credentials.json', scopes=[
    'https://www.googleapis.com/auth/spreadsheets'
])
gc = gspread.authorize(creds)
sh = gc.open_by_key('1VbyEQNuIAKpmTfk_5pTIjuLb3xlS-kdUfWflmfnFJSA')
ws = sh.worksheet('시트1')
rows = ws.get_all_records()

from collections import Counter
statuses = Counter(row.get('상태', '(빈칸)') or '(빈칸)' for row in rows)

order = ['대기', '발행대기', '발행완료', '발행중', '검수필요', '에러', '보류']
for s in order:
    if s in statuses:
        emoji = {'대기':'⏳','발행대기':'📝','발행완료':'✅','발행중':'🔄','검수필요':'⚠️','에러':'❌','보류':'⏸ '}.get(s,'  ')
        print(f'  {emoji} {s}: {statuses[s]}건')
for s, c in sorted(statuses.items()):
    if s not in order:
        print(f'     {s}: {c}건')
print(f'  ────────────')
print(f'  합계: {sum(statuses.values())}건')

# 발행대기 평균 본문 길이
ready = [row for row in rows if row.get('상태') == '발행대기']
if ready:
    avg_len = sum(len(str(r.get('본문마크다운', ''))) for r in ready) // len(ready)
    print(f'  발행대기 평균 본문: {avg_len}자')
" 2>/dev/null || echo -e "  ${RED}Sheets 조회 실패 (credentials.json 확인)${NC}"
echo

# === 7. 디스크 / 리소스 ===
echo -e "${YELLOW}[7] 리소스${NC}"
N8N_VOLUME=$(docker volume inspect blog-automation_n8n_data --format '{{.Mountpoint}}' 2>/dev/null || echo "?")
echo "  n8n 볼륨: $N8N_VOLUME"
DOCKER_SIZE=$(docker system df --format '{{.Type}}\t{{.Size}}' 2>/dev/null | head -3)
echo "  Docker 디스크:"
echo "$DOCKER_SIZE" | while IFS= read -r line; do echo "    $line"; done
echo

echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  점검 완료${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
