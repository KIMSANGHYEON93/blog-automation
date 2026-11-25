#!/bin/bash
# wake-scheduler 설치 — 사용자가 직접 `sudo bash scripts/wake/install.sh` 로 실행한다(에이전트는 실행 금지).
# 실행 전에 이 파일과 wake-scheduler.sh, plist 내용을 읽어 확인할 것.
#
# 하는 일: 스크립트·plist 를 root 소유로 /Library 아래에 "복사"하고(심볼릭 링크 아님) LaunchDaemon 으로 등록한다.
# 저장소 안 파일은 root 가 실행하지 않는다. 설치 후 저장소를 고쳐도 운영에는 반영되지 않는다(다시 설치해야 함).
set -euo pipefail
PATH=/usr/bin:/bin:/usr/sbin:/sbin

LABEL="com.blog-automation.wake-scheduler"
DEST_DIR="/Library/Application Support/blog-automation"
DEST_SCRIPT="$DEST_DIR/wake-scheduler.sh"
DEST_PLIST="/Library/LaunchDaemons/$LABEL.plist"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_SCRIPT="$SRC_DIR/wake-scheduler.sh"
SRC_PLIST="$SRC_DIR/$LABEL.plist"

if [ "$(id -u)" -ne 0 ]; then
    echo "root 권한이 필요합니다: sudo bash $0" >&2
    exit 1
fi
for src in "$SRC_SCRIPT" "$SRC_PLIST"; do
    if [ ! -f "$src" ] || [ -L "$src" ]; then
        echo "원본이 일반 파일이 아닙니다(심볼릭 링크 금지): $src" >&2
        exit 1
    fi
done
bash -n "$SRC_SCRIPT"
plutil -lint "$SRC_PLIST" >/dev/null

install -d -o root -g wheel -m 755 "$DEST_DIR"
install -o root -g wheel -m 755 "$SRC_SCRIPT" "$DEST_SCRIPT"
install -o root -g wheel -m 644 "$SRC_PLIST" "$DEST_PLIST"

# 설치된 사본이 원본과 같은지 확인(복사 중 바뀌지 않았는지)
cmp -s "$SRC_SCRIPT" "$DEST_SCRIPT" && cmp -s "$SRC_PLIST" "$DEST_PLIST"

launchctl bootout "system/$LABEL" 2>/dev/null || true
launchctl bootstrap system "$DEST_PLIST"
launchctl kickstart "system/$LABEL"

echo "설치 완료: $DEST_SCRIPT, $DEST_PLIST"
echo "확인: pmset -g sched   (00:55·08:55 깨우기가 앞으로 며칠치 보여야 합니다)"
sleep 2
pmset -g sched
