# n8n 보안 설정 적용·롤백 (2026-10-09)

`docker-compose.yml`과 워크플로 두 개(`workflow_complete.json`, `workflow_naver.json`)를 바꿨다.
저장소 파일만 바뀌었고 **실행 중인 컨테이너·n8n 워크플로에는 아직 반영되지 않았다.** 아래 순서로 사람이 직접 적용한다.

## 무엇이 바뀌었나

| 항목 | 전 | 후 | 이유 |
|------|----|----|------|
| 포트 | `5678:5678` (모든 인터페이스) | `127.0.0.1:5678:5678` | 같은 Wi-Fi의 다른 기기가 n8n 로그인 화면에 닿지 않게. 대시보드 '지금 생성'은 `docker exec`를 써서 영향 없음 |
| 환경변수 | `env_file: .env` (전부 주입) | 워크플로가 쓰는 키만 `environment`에 명시 | `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`라 Code 노드가 `$env`로 `KAKAO_PW`·`NAVER_LOGIN_PW`·`DASHBOARD_SECRET_KEY`·`TELEGRAM_BOT_TOKEN`까지 읽을 수 있었다 |
| `NODE_FUNCTION_ALLOW_BUILTIN` | `zlib` | `zlib,dns` | URL Validation 노드가 호스트를 DNS로 해석해 내부 IP를 거른다 |

`N8N_BLOCK_ENV_ACCESS_IN_NODE=false`는 유지한다. 워크플로가 `$env`를 쓰기 때문이다.

### 워크플로가 쓰는 `$env` 키 (전부 명시됨)

| 키 | 쓰는 곳 |
|----|---------|
| `LLM_PROVIDER` | Build LLM Request·Normalize Response (티스토리·네이버) |
| `SERPAPI_KEY` | SerpAPI Search / Naver Search (SerpAPI) |
| `FIRECRAWL_API_KEY` | Fetch Official Docs (없으면 직접 GET) |
| `UNSPLASH_ACCESS_KEY` | Inject Images (티스토리) |
| `SHEET_ID` | workflow_keyword_research.json, 옛 workflow.json |
| `GOOGLE_ADS_DEVELOPER_TOKEN`·`GOOGLE_ADS_CUSTOMER_ID`·`GOOGLE_ADS_LOGIN_CUSTOMER_ID` | workflow_keyword_research.json |
| `GOOGLE_SERVICE_ACCOUNT_EMAIL`·`GOOGLE_PRIVATE_KEY`·`GOOGLE_ADS_ACCESS_TOKEN` | get_access_token.js (키워드 리서치) |

다시 확인하는 명령: `grep -rhoE '\$env\.[A-Z_0-9]+' n8n/*.json n8n/code_nodes/ | sort -u`.
새 `$env` 키를 워크플로에 넣으면 `docker-compose.yml` `environment`에도 추가해야 한다(빠지면 빈 값).
Gemini 키·구글 서비스 계정은 n8n Credential(DB)에 있어 이 변경과 무관하다.

## 적용 순서

자동 실행 시각(티스토리 n8n 01:00, Pipeline B 08:30~14:30)을 피한다.

1. 백업
   ```bash
   docker exec <n8n컨테이너> n8n export:workflow --all --output=/home/node/.n8n/backup-$(date +%F).json
   cp docker-compose.yml docker-compose.yml.bak   # 롤백용 (git에도 있음)
   ```
2. 워크플로 가져오기 — **티스토리 워크플로는 가져오면 비활성화된다**
   ```bash
   docker cp n8n/workflow_complete.json <컨테이너>:/tmp/wc.json
   docker cp n8n/workflow_naver.json <컨테이너>:/tmp/wn.json
   docker exec <컨테이너> n8n import:workflow --input=/tmp/wc.json   # id ty52rqOEJ6ZjNF2L 유지
   docker exec <컨테이너> n8n import:workflow --input=/tmp/wn.json   # 네이버는 같은 id(SGXJWwyw6GW5aN6w)로 — 중복 생성 주의
   docker exec <컨테이너> n8n update:workflow --id=ty52rqOEJ6ZjNF2L --active=true
   ```
   네이버 워크플로는 비활성 그대로 둔다(대시보드 '지금 생성'으로만 실행).
   `workflow_naver.json`에는 id가 없으므로 UI에서 기존 워크플로를 열어 붙여넣거나, 파일에 `"id": "SGXJWwyw6GW5aN6w"`를 넣은 임시 사본으로 가져온다.
3. 컨테이너 다시 만들기 (환경변수·포트는 재생성해야 반영된다)
   ```bash
   docker compose up -d --force-recreate n8n
   ```
   `update:workflow --active=true`는 재시작 뒤에 반영되므로 이 단계가 2번 다음이어야 한다.
4. 확인
   - `docker exec <컨테이너> printenv | cut -d= -f1 | sort` 에 `KAKAO_PW`·`NAVER_LOGIN_PW`가 **없어야** 한다(값은 출력하지 말 것)
   - `lsof -nP -iTCP:5678 -sTCP:LISTEN` → `127.0.0.1:5678`
   - 대시보드 '지금 생성'으로 네이버 1건 → 시트 `URL검증` 칸이 `n/m (dead:x[, 확인실패:y][, 차단:z])` 형식인지
   - 다음 01:00 티스토리 실행 뒤 n8n 실행 기록에서 URL Validation 출력의 `url_validation.unverified_urls` 확인.
     모든 URL이 `DNS 확인 불가(n8n dns 모듈 미허용)`이면 3번의 `NODE_FUNCTION_ALLOW_BUILTIN`이 반영되지 않은 것이다

## 롤백

```bash
git checkout <이전 커밋> -- docker-compose.yml     # 또는 docker-compose.yml.bak 복원
docker compose up -d --force-recreate n8n
docker exec <컨테이너> n8n import:workflow --input=/home/node/.n8n/backup-<날짜>.json
docker exec <컨테이너> n8n update:workflow --id=ty52rqOEJ6ZjNF2L --active=true
docker compose restart n8n
```

## 남은 한계

- **DNS 재바인딩**: URL Validation은 DNS 해석 결과를 검사한 뒤 `this.helpers.httpRequest`가 다시 해석해 접속한다.
  그 사이 응답이 내부 IP로 바뀌면 막지 못한다(n8n 헬퍼에 IP를 고정할 방법이 없음). Python 캡처(`doc_capture.py`)도 같다.
- **응답 크기**: n8n `httpRequest`가 `maxContentLength`를 지키는지 확인하지 못했다. HEAD 우선, GET은 `Range: bytes=0-1023`과 URL당 15초 상한으로 줄였다.
- **헤드리스 브라우저**: 공식 문서 캡처는 최상위 주소와 도착 주소만 검사한다. 페이지 안 하위 리소스·스크립트 이동 요청은 통제하지 않는다(결과 화면은 버림).
  참고자료가 제품 도움말 등 임의 도메인이라 허용 목록으로 좁히면 기능이 깨져 적용하지 않았다.
- dns 모듈을 못 쓰면 URL Validation은 신뢰 도메인(공식 문서 목록)만 확인하고 나머지는 '확인 실패'로 남긴다(링크는 보존).
