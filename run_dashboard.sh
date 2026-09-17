#!/bin/bash
# 성과 대시보드 + 키워드 피라미드 + 파이프라인 로그 자동 업데이트

set -euo pipefail

PROJECT_DIR="${BLOG_PROJECT_DIR:-/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation}"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/dashboard_$(date +%Y%m%d_%H%M%S).log"
# launchd는 셸 초기화를 하지 않으므로 의존성이 설치된 인터프리터를 절대경로로 지정
PYTHON="${BLOG_PYTHON:-/Users/kimsanghyeon/.pyenv/versions/3.11.11/bin/python3}"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

echo "=== Dashboard 업데이트 시작: $(date '+%Y-%m-%d %H:%M:%S') ===" | tee "$LOG_FILE"

EXIT_CODE=0
"$PYTHON" scripts/update_dashboard.py >> "$LOG_FILE" 2>&1 || EXIT_CODE=$?

echo "=== Dashboard 업데이트 종료: $(date '+%Y-%m-%d %H:%M:%S') (exit=$EXIT_CODE) ===" | tee -a "$LOG_FILE"

find "$LOG_DIR" -name "dashboard_*.log" -mtime +30 -delete 2>/dev/null || true

exit $EXIT_CODE
