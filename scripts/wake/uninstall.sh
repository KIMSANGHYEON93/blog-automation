#!/bin/bash
# wake-scheduler 제거(롤백) — 사용자가 직접 `sudo bash scripts/wake/uninstall.sh` 로 실행한다.
# LaunchDaemon·root 스크립트·로그를 지우고, 이 스크립트가 예약한 00:55·08:55 깨우기도 취소한다.
# 다른 프로그램이 예약한 깨우기는 건드리지 않는다(시각이 00:55:00·08:55:00 이고 'pmset' 소유인 것만).
set -euo pipefail
PATH=/usr/bin:/bin:/usr/sbin:/sbin

LABEL="com.blog-automation.wake-scheduler"
DEST_DIR="/Library/Application Support/blog-automation"
DEST_PLIST="/Library/LaunchDaemons/$LABEL.plist"
LOG="/var/log/blog-automation-wake.log"

if [ "$(id -u)" -ne 0 ]; then
    echo "root 권한이 필요합니다: sudo bash $0" >&2
    exit 1
fi

launchctl bootout "system/$LABEL" 2>/dev/null || true

pmset -g sched | sed -n "s/.*wake at \([0-9/]* \(00:55:00\|08:55:00\)\) by 'pmset'.*/\1/p" |
while IFS= read -r stamp; do
    pmset schedule cancel wake "$stamp"
    echo "깨우기 예약 취소: $stamp"
done

rm -f "$DEST_PLIST" "$DEST_DIR/wake-scheduler.sh" "$LOG"
rmdir "$DEST_DIR" 2>/dev/null || true

echo "제거 완료. 확인: pmset -g sched"
pmset -g sched
