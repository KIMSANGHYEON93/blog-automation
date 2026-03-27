#!/bin/bash
# schedule_wake.sh — 내일 Pipeline A/B 실행 전 Mac wake 예약
# 매일 자정에 launchd로 실행되어 다음날 wake 이벤트 2건을 등록
#
# 사용법 (1회):
#   sudo bash scripts/schedule_wake.sh
#
# launchd 등록:
#   sudo cp scripts/com.blog-automation.wake-scheduler.plist /Library/LaunchDaemons/
#   sudo launchctl load /Library/LaunchDaemons/com.blog-automation.wake-scheduler.plist

set -euo pipefail

# 내일 날짜 (macOS date)
TOMORROW=$(date -v+1d "+%m/%d/%Y")

# 기존 blog-automation wake 이벤트 취소 (에러 무시)
pmset repeat cancel 2>/dev/null || true

# Pipeline A: 00:55 wake, Pipeline B: 08:55 wake
# pmset repeat는 이벤트 1개만 지원 → pmset schedule로 개별 등록
pmset schedule wake "${TOMORROW} 00:55:00"
pmset schedule wake "${TOMORROW} 08:55:00"

echo "[$(date)] Wake 예약 완료: ${TOMORROW} 00:55, 08:55"
