#\!/bin/bash
pmset schedule cancelall 2>/dev/null
TOMORROW=$(date -v+1d +"%m/%d/%Y")
pmset schedule wake "$TOMORROW 00:55:00"
pmset schedule wake "$TOMORROW 08:55:00"
echo "[$(date)] Wake 예약 완료: $TOMORROW 00:55, 08:55"
