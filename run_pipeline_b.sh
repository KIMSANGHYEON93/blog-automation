#!/bin/bash
# Pipeline B — 티스토리 블로그 자동화 워커
# 인자 없으면 기본 발행, 인자 있으면 해당 서브커맨드 실행
# 사용법: ./run_pipeline_b.sh [--revise|--check-index|--submit-index|...]

set -euo pipefail

PROJECT_DIR="${BLOG_PROJECT_DIR:-/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation}"
LOG_DIR="${PROJECT_DIR}/logs"
# launchd는 셸 초기화를 하지 않으므로 의존성이 설치된 인터프리터를 절대경로로 지정
PYTHON="${BLOG_PYTHON:-/Users/kimsanghyeon/.pyenv/versions/3.11.11/bin/python3}"

# 작업명 추출 (로그 파일명용)
TASK_NAME="publish"
if [[ $# -gt 0 ]]; then
    TASK_NAME="${1#--}"  # --revise → revise
    TASK_NAME="${TASK_NAME//-/_}"  # check-index → check_index
fi

LOG_FILE="${LOG_DIR}/${TASK_NAME}_$(date +%Y%m%d_%H%M%S).log"

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

# 프로젝트 디렉토리로 이동 (credentials.json, .browser_data 상대경로 해결)
cd "$PROJECT_DIR"

# --- Fix 1: 파이프라인 동시 실행 방지 (mkdir atomic lock) ---
LOCK_DIR="${PROJECT_DIR}/.pipeline_b.lock"
LOCK_OWNER="${LOCK_DIR}/owner"  # 잡은 프로세스 PID (대시보드 DirectoryPipelineLock과 같은 규약)
lock_is_stale() {
    local pid
    pid="$(cat "$LOCK_OWNER" 2>/dev/null || true)"
    if [[ -n "$pid" ]]; then
        # 소유 프로세스가 죽었거나, 살아 있어도 하루가 넘으면(PID 재사용) 스테일
        ! kill -0 "$pid" 2>/dev/null || find "$LOCK_DIR" -maxdepth 0 -mmin +1440 2>/dev/null | grep -q .
    else
        # 예전 형식(owner 없음): 5시간 이상 → 스테일
        find "$LOCK_DIR" -maxdepth 0 -mmin +300 2>/dev/null | grep -q .
    fi
}
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    if lock_is_stale; then
        rm -f "$LOCK_OWNER"
        rmdir "$LOCK_DIR" 2>/dev/null || true
        mkdir "$LOCK_DIR" 2>/dev/null || { echo "[SKIP] 다른 파이프라인 실행 중 — ${TASK_NAME} 스킵" | tee -a "$LOG_FILE"; exit 0; }
    else
        echo "[SKIP] 다른 파이프라인 실행 중 — ${TASK_NAME} 스킵" | tee -a "$LOG_FILE"
        exit 0
    fi
fi
echo $$ > "$LOCK_OWNER"
trap 'rm -f "$LOCK_OWNER"; rmdir "$LOCK_DIR" 2>/dev/null' EXIT

echo "=== Pipeline B [${TASK_NAME}] 시작: $(date '+%Y-%m-%d %H:%M:%S') ===" | tee "$LOG_FILE"

# CLI 실행 (인자 그대로 전달)
# set -e 상태에서도 실패 시 정리 단계까지 진행하도록 종료 코드를 직접 수집
EXIT_CODE=0
"$PYTHON" -m src.interface.cli "$@" >> "$LOG_FILE" 2>&1 || EXIT_CODE=$?

# --- Fix 4: 좀비 ChromeDriver/Chrome 정리 (안전망) ---
pkill -f "user-data-dir=.*blog-automation.*browser_data" 2>/dev/null || true

echo "=== Pipeline B [${TASK_NAME}] 종료: $(date '+%Y-%m-%d %H:%M:%S') (exit=$EXIT_CODE) ===" | tee -a "$LOG_FILE"

# 오래된 로그 정리 (30일 이상)
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null || true

exit $EXIT_CODE
