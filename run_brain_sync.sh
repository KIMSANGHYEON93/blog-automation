#!/bin/bash
# AI-Brain 볼트 → 시트 'AI브레인용어' 탭 동기화 (launchd 주간 실행)
# 사용법: ./run_brain_sync.sh [--dry-run]

set -euo pipefail

PROJECT_DIR="${BLOG_PROJECT_DIR:-/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation}"
LOG_DIR="${PROJECT_DIR}/logs"
# launchd는 셸 초기화를 하지 않으므로 의존성이 설치된 인터프리터를 절대경로로 지정
PYTHON="${BLOG_PYTHON:-/Users/kimsanghyeon/.pyenv/versions/3.11.11/bin/python3}"
# .env에 BRAIN_VAULT_FOLDER_ID가 있으면 그 값이 우선한다
VAULT_ID="${BRAIN_VAULT_FOLDER_ID:-19MxcgD4jAi95-QjxnUMJraV8svkj9Bew}"

LOG_FILE="${LOG_DIR}/brain_sync_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

echo "=== AI-Brain 용어 동기화 시작: $(date '+%Y-%m-%d %H:%M:%S') ===" | tee "$LOG_FILE"

EXIT_CODE=0
"$PYTHON" scripts/sync_brain_terms.py --vault-folder-id "$VAULT_ID" "$@" >> "$LOG_FILE" 2>&1 || EXIT_CODE=$?

echo "=== 종료: $(date '+%Y-%m-%d %H:%M:%S') (exit=$EXIT_CODE) ===" | tee -a "$LOG_FILE"
find "$LOG_DIR" -name "brain_sync_*.log" -mtime +30 -delete 2>/dev/null || true

exit $EXIT_CODE
