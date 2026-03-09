#!/bin/bash
# Pipeline B — 티스토리 자동 발행 워커
# Cron: 매일 09:00 AM (Asia/Seoul)
# 동작: Google Sheets에서 상태=발행대기 글을 읽어 티스토리에 발행

set -euo pipefail

PROJECT_DIR="/Users/kimsanghyeon/Documents/GitHub/Core Web Vitals/blog-automation"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/pipeline_b_$(date +%Y%m%d_%H%M%S).log"
PYTHON="/opt/homebrew/bin/python3"

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

# 프로젝트 디렉토리로 이동 (credentials.json, .browser_data 상대경로 해결)
cd "$PROJECT_DIR"

echo "=== Pipeline B 시작: $(date '+%Y-%m-%d %H:%M:%S') ===" | tee "$LOG_FILE"

# Pipeline B 워커 실행
$PYTHON -m src.interface.cli >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

echo "=== Pipeline B 종료: $(date '+%Y-%m-%d %H:%M:%S') (exit=$EXIT_CODE) ===" | tee -a "$LOG_FILE"

# 오래된 로그 정리 (30일 이상)
find "$LOG_DIR" -name "pipeline_b_*.log" -mtime +30 -delete 2>/dev/null || true

exit $EXIT_CODE
