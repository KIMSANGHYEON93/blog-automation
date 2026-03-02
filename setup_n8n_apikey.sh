#!/bin/bash
# n8n Docker 컨테이너에서 API 키를 생성하고 /tmp/n8n_api_key.txt에 저장
# 사용법: ./setup_n8n_apikey.sh
set -euo pipefail

N8N_CONTAINER="blog-automation-n8n-1"
API_KEY_FILE="/tmp/n8n_api_key.txt"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo "=== n8n API 키 설정 ==="

# 1. 컨테이너 실행 확인
if ! docker ps --format '{{.Names}}' | grep -q "$N8N_CONTAINER"; then
    echo -e "${RED}ERROR: n8n 컨테이너($N8N_CONTAINER)가 실행 중이 아닙니다.${NC}"
    echo "  docker compose up -d 를 먼저 실행하세요."
    exit 1
fi

# 2. 기존 키 확인
if [ -f "$API_KEY_FILE" ]; then
    EXISTING_KEY=$(cat "$API_KEY_FILE")
    # 기존 키가 유효한지 테스트
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        "http://localhost:5678/api/v1/workflows" \
        -H "X-N8N-API-KEY: $EXISTING_KEY" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}기존 API 키가 유효합니다.${NC}"
        echo "  파일: $API_KEY_FILE"
        exit 0
    fi
    echo "기존 키가 유효하지 않음 — 새로 생성합니다."
fi

# 3. n8n CLI로 API 키 생성
echo "n8n 컨테이너에서 API 키 생성 중..."
API_KEY=$(docker exec "$N8N_CONTAINER" n8n user-management:create-api-key 2>/dev/null || true)

if [ -z "$API_KEY" ]; then
    # 대안: n8n 환경변수에서 읽기
    API_KEY=$(docker exec "$N8N_CONTAINER" printenv N8N_API_KEY 2>/dev/null || true)
fi

if [ -z "$API_KEY" ]; then
    echo -e "${RED}API 키 자동 생성 실패.${NC}"
    echo "수동으로 설정하세요:"
    echo "  1. http://localhost:5678 접속 → Settings → API"
    echo "  2. API 키 복사 후: echo 'YOUR_KEY' > $API_KEY_FILE"
    exit 1
fi

# 4. 파일에 저장
echo "$API_KEY" > "$API_KEY_FILE"
chmod 600 "$API_KEY_FILE"
echo -e "${GREEN}API 키 저장 완료: $API_KEY_FILE${NC}"

# 5. 검증
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    "http://localhost:5678/api/v1/workflows" \
    -H "X-N8N-API-KEY: $API_KEY" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}API 키 검증 성공 (HTTP 200)${NC}"
else
    echo -e "${RED}API 키 검증 실패 (HTTP $HTTP_CODE) — 수동 확인 필요${NC}"
fi
