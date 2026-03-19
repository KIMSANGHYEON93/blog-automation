# 실행 방법 가이드

## 목차

1. [사전 준비](#1-사전-준비)
2. [환경 변수 설정](#2-환경-변수-설정)
3. [Pipeline A 실행 (콘텐츠 생성)](#3-pipeline-a-실행-콘텐츠-생성)
4. [Pipeline B 실행 (자동 발행)](#4-pipeline-b-실행-자동-발행)
5. [보조 명령어](#5-보조-명령어)
6. [유틸리티 스크립트](#6-유틸리티-스크립트)
7. [자동화 (Cron)](#7-자동화-cron)
8. [모니터링](#8-모니터링)
9. [트러블슈팅](#9-트러블슈팅)

---

## 1. 사전 준비

### 필수 요구사항

| 항목 | 버전 | 용도 |
|------|------|------|
| Python | 3.9+ | Pipeline B 실행 |
| Docker & Docker Compose | 최신 | Pipeline A (n8n) 실행 |
| Chrome | 최신 | SeleniumBase 브라우저 자동화 |
| Google Cloud 서비스 계정 | - | Sheets API + Search Console |

### 설치

```bash
cd blog-automation

# Python 의존성 설치
pip install -e ".[dev]"

# n8n Docker 컨테이너 시작
docker compose up -d
```

### Google 서비스 계정 설정

1. [Google Cloud Console](https://console.cloud.google.com/) → 프로젝트 생성
2. Sheets API, Search Console API 활성화
3. 서비스 계정 생성 → JSON 키 다운로드 → `credentials.json`으로 저장
4. Google Sheets에 서비스 계정 이메일을 **편집자** 권한으로 공유

---

## 2. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일의 주요 항목:

### 필수

```env
# 카카오 계정 (티스토리 로그인)
KAKAO_ID=example@kakao.com
KAKAO_PW=your_password

# 티스토리 블로그 이름 (xxx.tistory.com의 xxx 부분)
TISTORY_BLOG=your-blog

# Google Sheets 연동
GOOGLE_CREDS=credentials.json
SHEET_NAME=keyword_calendar_v2
```

### 발행 설정

```env
MAX_POSTS=5          # 1회 실행 시 최대 발행 수
HEADLESS=true        # true: 백그라운드 / false: 브라우저 표시
MIN_DELAY=300        # 발행 간 최소 대기 (초)
MAX_DELAY=900        # 발행 간 최대 대기 (초)
```

### API 키

```env
LLM_PROVIDER=gemini              # gemini 또는 claude
GEMINI_API_KEY=your_key          # Pipeline A LLM
SERPAPI_KEY=your_key             # SERP 검색 데이터
PAGESPEED_API_KEY=your_key       # CWV 성능 측정
```

### 선택 사항

```env
SITE_PROFILE=site_profile.json   # 카테고리 매핑 파일
CWV_CHECK=true                   # 발행 후 CWV 자동 점검
RETRY_FAILED=false               # 실패 글 자동 재시도
SLACK_WEBHOOK_URL=               # Slack 알림
TELEGRAM_BOT_TOKEN=              # Telegram 알림
TELEGRAM_CHAT_ID=
```

---

## 3. Pipeline A 실행 (콘텐츠 생성)

> n8n 워크플로우 기반. Google Sheets에서 "대기" 상태 키워드를 읽어 LLM으로 콘텐츠를 생성하고 "발행대기"로 전환.

### 자동 실행 (권장)

n8n 내장 Schedule Trigger가 매일 01:00 AM에 자동 실행합니다.

```bash
# n8n 컨테이너 시작 (이미 실행 중이면 생략)
docker compose up -d

# n8n 웹 UI 접속
open http://localhost:5678
# 기본 계정: admin / changeme (N8N_PASSWORD 환경변수로 변경 가능)
```

### 수동 실행

```bash
# Docker CLI로 즉시 실행
docker exec -it blog-automation-n8n-1 \
  n8n execute --id <WORKFLOW_ID>
```

### 워크플로우 임포트 (최초 1회)

```bash
# 방법 1: n8n CLI
docker exec -it blog-automation-n8n-1 \
  n8n import:workflow --input=/host/path/n8n/workflow_complete.json

# 방법 2: n8n 웹 UI
# Settings → Import from File → n8n/workflow_complete.json 선택
```

### Pipeline A 처리 흐름

```
Google Sheets (상태=대기)
  → SERP 검색 (SerpAPI)
  → 키워드 유형 판별 (용어/비교/에러해결)
  → 프롬프트 라우팅 → LLM 콘텐츠 생성
  → JSON 파싱 + 구조 검증
  → 교차 검증 (Claude Haiku)
  → Sheets 업데이트 (상태=발행대기)
```

---

## 4. Pipeline B 실행 (자동 발행)

> Python/SeleniumBase 기반. Google Sheets에서 "발행대기" 글을 읽어 티스토리에 자동 발행.

### 기본 실행 (발행)

```bash
# 기본 발행 (고스트 복구 → 발행 → CWV 점검)
python -m src.interface.cli

# 브라우저 표시 모드 (디버깅용)
HEADLESS=false python -m src.interface.cli

# 최대 발행 수 조정
MAX_POSTS=3 python -m src.interface.cli
```

### 첫 실행 시 주의사항

카카오 2FA 인증이 필요합니다. **반드시 브라우저 표시 모드**로 실행하세요:

```bash
HEADLESS=false python -m src.interface.cli
```

1. 브라우저가 열리면 카카오 로그인 페이지 표시
2. 카카오톡 앱에서 2FA 승인
3. 이후 쿠키가 `.browser_data/`에 저장되어 자동 로그인

### Pipeline B 처리 흐름

```
Google Sheets (상태=발행대기)
  → 고스트 복구 (발행중 상태 롤백)
  → 카테고리 자동 분류
  → 카카오 로그인 → 티스토리 에디터 열기
  → Markdown → HTML 변환
  → SEO 최적화 (lazy loading, nofollow, FAQ JSON-LD)
  → 내부 링크 자동 삽입
  → 에디터에 콘텐츠 주입
  → API 발행 (+ React fallback)
  → 공개 상태 검증 + 비공개 자동 복구
  → Sheets 업데이트 (상태=발행완료, URL 기록)
  → CWV 점검 (PageSpeed API)
```

---

## 5. 보조 명령어

모든 명령은 `blog-automation/` 디렉토리에서 실행합니다.

### 글 수정 (수정대기 → 기존 글 업데이트)

```bash
python -m src.interface.cli --revise
```

수정대기 상태의 포스트를 기존 티스토리 글에 업데이트합니다.

### 색인 점검 (Google Search Console)

```bash
python -m src.interface.cli --check-index
```

발행완료 포스트의 Google 색인 상태를 점검합니다. 미색인 글은 수정대기로 전환합니다.

### 색인 제출 (Google Indexing API)

```bash
python -m src.interface.cli --submit-index
```

발행완료 포스트를 Google Indexing API에 색인 요청합니다.

### 사이트맵 생성

```bash
python -m src.interface.cli --generate-sitemap
```

발행완료 포스트로 `sitemap.xml` 파일을 생성합니다.

### 블로그 현황 대시보드

```bash
python -m src.interface.cli --status
```

상태별 포스트 수, 발행률, 실패률 등을 터미널에 출력합니다.

### 키워드 자동 발굴

```bash
python -m src.interface.cli --discover-keywords
```

Google Search Console 데이터에서 새 키워드를 발굴합니다.

### 카테고리 동기화

```bash
# 확인만
python -m src.interface.cli --sync-categories

# 자동 갱신
python -m src.interface.cli --sync-categories --auto-update
```

티스토리의 실제 카테고리와 `site_profile.json`을 비교/동기화합니다.

### 실패 글 일괄 복구

```bash
python -m src.interface.cli --recover-failed
```

발행실패 포스트를 에러 유형별로 분류하고, 자동 복구 가능한 건은 발행대기로 전환합니다.

### AdSense 필수 페이지 발행

```bash
python -m src.interface.cli --publish-pages
```

소개, 개인정보처리방침, 문의 페이지를 자동 생성하여 발행합니다.

---

## 6. 유틸리티 스크립트

### 성과 대시보드 업데이트

```bash
# 미리보기
python scripts/update_dashboard.py --dry-run

# 실행
python scripts/update_dashboard.py
```

Google Sheets의 성과 대시보드, 키워드 피라미드, 파이프라인 로그, 사용 가이드 탭을 자동 업데이트합니다.

### 키워드 일괄 추가

```bash
# 미리보기
python scripts/add_keywords.py --dry-run

# 실행
python scripts/add_keywords.py
```

새 키워드를 Google Sheets에 일괄 추가합니다.

---

## 7. 자동화 (Cron)

### crontab 설정

```bash
crontab -e
```

```cron
# Pipeline A: n8n 자체 스케줄러 (01:00 AM, Docker 내장)
# Pipeline B: cron으로 매일 09:00 AM 실행
0 9 * * * /path/to/blog-automation/run_pipeline_b.sh >> /path/to/logs/cron.log 2>&1
```

### 실행 스크립트 (run_pipeline_b.sh)

```bash
#!/bin/bash
cd /path/to/blog-automation
source .env
python -m src.interface.cli
```

---

## 8. 모니터링

### 상태 확인 스크립트

```bash
# 전체 파이프라인 상태 점검
./check_status.sh

# 최근 실행 결과
./check_last_run.sh
```

### 로그 확인

```bash
# Pipeline B 로그
tail -100 logs/blog-publisher.log

# n8n 로그
docker compose logs --tail=50 n8n
```

### 알림 설정

`.env`에 Slack 또는 Telegram 웹훅을 설정하면 발행 결과를 알림으로 받을 수 있습니다:

```env
# Slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# 또는 Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

---

## 9. 트러블슈팅

### 카카오 2FA 반복 요구

쿠키를 삭제하고 브라우저 표시 모드로 재인증:

```bash
rm -rf .browser_data/
HEADLESS=false python -m src.interface.cli
```

### 발행 시 script timeout 오류

API 발행 타임아웃 시 자동으로 2회 재시도합니다. 반복 실패 시:

1. 네트워크 상태 확인
2. 티스토리 서버 점검 여부 확인
3. `MIN_DELAY` / `MAX_DELAY` 값을 늘려서 재실행

### n8n 워크플로우 실행 실패

```bash
# Docker 상태 확인
docker compose ps

# 컨테이너 재시작
docker compose restart n8n

# n8n 로그 확인
docker compose logs --tail=100 n8n
```

### Pipeline B 본문 누락

`.browser_data/` 삭제 후 재실행:

```bash
rm -rf .browser_data/
HEADLESS=false python -m src.interface.cli
```

### 일일 발행 제한 (15건)

티스토리는 하루 최대 15건까지 공개 발행 가능합니다. 초과 시 `DailyPublishLimitError`가 발생하고 배치가 자동 중단됩니다. 다음 날 자동으로 재개됩니다.

### 품질 검증 실패

```bash
# 전체 품질 게이트 실행
make quality

# 개별 검증
make test-unit        # 단위 테스트
make lint             # 코드 스타일
make typecheck        # 타입 체크
make validate-ddd     # DDD 레이어 규칙
make coverage         # 커버리지 (80% 이상)
```
