#!/bin/bash
# 맥이 잠든 밤에도 launchd 작업이 돌도록 다음 며칠의 깨우기(pmset schedule wake)를 예약한다.
#
# root(LaunchDaemon)로 실행된다. 최소 권한 원칙:
#   - 하는 일은 `pmset schedule wake` 등록뿐이다. 인자·환경변수·설정 파일을 읽지 않는다.
#   - 경로와 시각은 이 파일에 고정돼 있다. root 소유 위치(/Library/Application Support/...)에
#     설치된 사본만 실행한다(scripts/wake/install.sh). 사용자가 쓸 수 있는 경로의 사본은 실행 금지.
#   - 이미 예약된 시각은 건너뛴다(멱등). 지난 시각은 예약하지 않는다.
set -euo pipefail
PATH=/usr/bin:/bin:/usr/sbin:/sbin
PMSET=/usr/bin/pmset

WAKE_TIMES=("00:55:00" "08:55:00")  # 01:00 n8n 생성 / 09:00 발행 5분 전
DAYS_AHEAD=3                        # 오늘 포함 오늘+3일까지(하루 이틀 실행이 빠져도 이어지게)

existing="$("$PMSET" -g sched)"
now="$(date +%s)"

for offset in $(seq 0 "$DAYS_AHEAD"); do
    day="$(date -v+"${offset}"d +%m/%d/%Y)"
    for time in "${WAKE_TIMES[@]}"; do
        stamp="$day $time"
        epoch="$(date -j -f "%m/%d/%Y %H:%M:%S" "$stamp" +%s)"
        if [ "$epoch" -le "$now" ]; then
            continue
        fi
        if grep -q "wake at $stamp" <<<"$existing"; then
            continue
        fi
        "$PMSET" schedule wake "$stamp"
        echo "[$(date '+%F %T')] 깨우기 예약: $stamp"
    done
done
