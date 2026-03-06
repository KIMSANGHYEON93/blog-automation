# Blog Automation — B2B IT 블로그 자동화 시스템

> 키워드 입력부터 콘텐츠 생성, 품질 검증, 티스토리 발행까지 전 과정을 자동화하는 풀스택 파이프라인

## 개요

B2B IT 인프라 블로그를 자동으로 운영하기 위한 시스템입니다. 두 개의 파이프라인이 연동되어, 매일 새벽 키워드 기반 콘텐츠를 생성하고 오전에 자동 발행합니다.

```
Pipeline A (n8n)                    Pipeline B (Python/SeleniumBase)
┌──────────────────────┐            ┌──────────────────────────┐
│ 01:00 AM (자동 실행)  │            │ 09:00 AM (자동 실행)      │
│                      │            │                          │
│ Google Sheets 읽기   │            │ Google Sheets 읽기        │
│       ↓              │            │ (상태=발행대기)            │
│ SERP 검색 (SerpAPI)  │            │       ↓                  │
│       ↓              │            │ 카카오 로그인              │
│ 프롬프트 라우팅       │            │       ↓                  │
│ (용어/비교/에러해결)   │            │ 티스토리 에디터 열기       │
│       ↓              │            │       ↓                  │
│ LLM 콘텐츠 생성      │            │ 본문 + 태그 + FAQ 주입    │
│ (Gemini/Claude 전환)  │            │       ↓                  │
│       ↓              │            │ 공개 발행                 │
│ JSON 파싱 + 복구     │            │       ↓                  │
│       ↓              │            │ Sheets 상태 업데이트       │
│ 구조 검증            │            │ (발행완료 + URL 기록)      │
│       ↓              │            └──────────────────────────┘
│ 교차 검증 (Haiku)    │
│       ↓              │
│ Sheets 업데이트       │
│ (상태=발행대기)       │
└──────────────────────┘
```

## 주요 특징

- **DDD 4-Layer 아키텍처**: Domain, Application, Infrastructure, Interface 계층 분리로 유지보수성 확보
- **TDD 기반 개발**: 75건 테스트 통과, 커버리지 92%+
- **LLM Provider 추상화**: `.env`의 `LLM_PROVIDER` 값 하나로 Gemini/Claude 전환 (워크플로우 수정 불필요)
- **3종 프롬프트 자동 라우팅**: 키워드 유형(용어/비교/에러해결)에 따라 최적화된 프롬프트 자동 선택
- **Lenient JSON 파서**: LLM이 생성하는 비정형 JSON을 자동 복구하는 재귀 하강 파서 내장
- **4항목 교차 검증**: 정확성, 논리성, 완성도, 유용성을 별도 LLM으로 검증
- **FAQ JSON-LD 자동 주입**: Google 리치 스니펫 대응
- **고스트 복구**: 발행 중 장애 시 자동 상태 롤백 (발행중 → 발행대기)

## 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.9+ |
| 아키텍처 | DDD 4-Layer (Hexagonal) |
| 워크플로우 엔진 | n8n 1.76.1 (Docker) |
| 브라우저 자동화 | SeleniumBase 4.25+ |
| 데이터 저장소 | Google Sheets (gspread) |
| LLM (콘텐츠 생성) | Gemini 2.0 Flash / Claude Sonnet 4.5 (전환 가능) |
| LLM (교차 검증) | Claude Haiku |
| 검색 데이터 | SerpAPI |
| 린트/타입 체크 | ruff, mypy |
| 테스트 | pytest (75건, 커버리지 92%) |

## 디렉토리 구조

```
blog-automation/
├── src/
│   ├── domain/                     # 핵심 비즈니스 로직 (외부 의존성 0)
│   │   ├── entities/post.py        # Post 엔티티 + 상태 머신
│   │   ├── value_objects/          # PostStatus, PostContent, PublishResult 등
│   │   ├── ports/                  # PostRepository, BrowserPort (인터페이스)
│   │   ├── services/               # PublishPolicy 도메인 서비스
│   │   └── exceptions.py           # 도메인 예외 계층
│   ├── application/                # 유스케이스 (Domain만 의존)
│   │   ├── use_cases/
│   │   │   ├── publish_posts.py    # 발행 유스케이스
│   │   │   └── reset_stuck_posts.py # 고스트 복구 유스케이스
│   │   └── dto.py                  # PublishBatchResult DTO
│   ├── infrastructure/             # 외부 시스템 어댑터 (Port 구현)
│   │   ├── browser/
│   │   │   ├── tistory_editor.py   # 티스토리 에디터 조작
│   │   │   ├── kakao_auth.py       # 카카오 로그인
│   │   │   ├── selenium_adapter.py # BrowserPort 구현체
│   │   │   ├── dom_selectors.py    # DOM 셀렉터 (Fallback Chain)
│   │   │   └── js_injector.py      # JavaScript 주입
│   │   ├── persistence/
│   │   │   ├── google_sheets_repo.py  # PostRepository 구현체
│   │   │   └── in_memory_repo.py      # 테스트용 InMemory 구현
│   │   └── config.py               # 환경 설정
│   └── interface/
│       └── cli.py                  # Composition Root (진입점)
├── n8n/                            # Pipeline A (콘텐츠 생성)
│   ├── workflow_complete.json      # n8n 워크플로우 정의
│   ├── prompts/
│   │   ├── prompt_a_terminology.md # 용어 정의 프롬프트
│   │   ├── prompt_b_comparison.md  # 비교 분석 프롬프트
│   │   ├── prompt_c_troubleshooting.md # 에러 해결 프롬프트
│   │   └── prompt_d_verification.md    # 교차 검증 프롬프트
│   └── code_nodes/
│       ├── route_prompt.js         # 키워드 유형 판별 + 프롬프트 라우팅
│       ├── build_llm_request.js    # LLM Provider별 요청 빌더
│       ├── normalize_llm_response.js # LLM 응답 정규화
│       ├── parse_json.js           # JSON 파싱 + Lenient 복구 파서
│       ├── parse_serp.js           # SERP 데이터 구조화
│       ├── parse_verification.js   # 교차 검증 결과 판정
│       ├── validate_structure.js   # 마크다운 구조 검증
│       ├── validate_urls.js        # URL 유효성 검증
│       ├── inject_images.js        # 이미지 자동 삽입
│       └── lint_code_blocks.js     # 코드블록 린트
├── tests/
│   ├── unit/                       # 단위 테스트 (66건)
│   │   ├── domain/                 # 엔티티, VO, 정책 테스트
│   │   └── application/            # 유스케이스 테스트
│   ├── integration/                # 통합 테스트 (9건)
│   └── e2e/                        # E2E 테스트
├── docker-compose.yml              # n8n Docker 설정
├── Makefile                        # 테스트/린트/품질 명령어
├── pyproject.toml                  # 프로젝트 설정
├── run_pipeline_b.sh               # Pipeline B cron 실행 스크립트
├── check_status.sh                 # 파이프라인 상태 모니터링
├── check_last_run.sh               # 최근 실행 결과 확인
├── masterplan_v2.3.md              # 마스터 플랜
└── prosess.md                      # 개발 프로세스 추적 로그
```

## 설치 및 설정

### 사전 요구사항

- Python 3.9+
- Docker & Docker Compose
- Google Cloud 서비스 계정 (Sheets API)
- Chrome 브라우저

### 1. 저장소 클론 및 의존성 설치

```bash
git clone <repository-url>
cd blog-automation

# Python 의존성
pip install -e ".[dev]"

# n8n (Docker)
docker-compose up -d
```

### 2. 환경 변수 설정

`.env.example`을 `.env`로 복사 후 값을 채워 넣습니다.

```bash
cp .env.example .env
```

```env
# 카카오 계정 (티스토리 로그인용)
KAKAO_ID=your_kakao_id
KAKAO_PW=your_kakao_password

# 티스토리 블로그 이름
TISTORY_BLOG=your-blog-name

# Google Sheets
GOOGLE_CREDS=credentials.json
SHEET_NAME=keyword_calendar_v2

# 발행 설정
MAX_POSTS=5
HEADLESS=true
MIN_DELAY=300
MAX_DELAY=900

# LLM Provider (gemini 또는 claude)
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
# CLAUDE_API_KEY=your_claude_api_key  # Claude 사용 시

# 검색 데이터
SERPAPI_KEY=your_serpapi_key
```

### 3. Google Sheets 서비스 계정 설정

1. Google Cloud Console에서 서비스 계정 생성
2. Sheets API 활성화
3. 서비스 계정 키(JSON) 다운로드 → `credentials.json`으로 저장
4. 대상 스프레드시트에 서비스 계정 이메일 공유(편집자 권한)

### 4. n8n 워크플로우 임포트

```bash
# n8n 실행 확인
docker-compose ps

# 워크플로우 임포트 (n8n REST API 사용)
curl -X POST http://localhost:5678/api/v1/workflows \
  -H "Content-Type: application/json" \
  -d @n8n/workflow_complete.json
```

n8n 웹 UI(`http://localhost:5678`)에서 워크플로우를 활성화합니다.

## 사용 방법

### 수동 실행

```bash
# Pipeline B 단독 실행 (발행대기 글 발행)
python -m src.interface.cli

# 헤드리스 비활성화 (브라우저 동작 확인용)
HEADLESS=false python -m src.interface.cli
```

### 자동 실행 (Cron)

시스템에 등록된 자동 스케줄:

| 파이프라인 | 시간 | 동작 |
|-----------|------|------|
| Pipeline A (n8n) | 매일 01:00 AM | 키워드 → 콘텐츠 생성 → Sheets 저장 |
| Pipeline B (Python) | 매일 09:00 AM | Sheets → 티스토리 발행 |

```bash
# crontab 등록 예시
0 9 * * * /path/to/blog-automation/run_pipeline_b.sh
```

### 모니터링

```bash
# 전체 파이프라인 상태 점검
./check_status.sh

# 최근 실행 결과 확인
./check_last_run.sh

# Pipeline B 로그 확인
tail -50 logs/pipeline_b_*.log
```

## 테스트

```bash
# 단위 테스트 (Domain + Application)
make test-unit

# 통합 테스트 (Google Sheets + Selenium)
make test-integ

# 전체 테스트
make test-all

# 커버리지 리포트 (80% 이상 필수)
make coverage

# 린트 + 타입 체크
make lint
make typecheck

# DDD 레이어 규칙 검증
make validate-ddd

# 전체 품질 게이트 (테스트 + 커버리지 + 린트 + 타입 + DDD)
make quality
```

## 아키텍처

### DDD 4-Layer + 의존성 역전

```
┌─────────────────────────────────────────┐
│           Interface Layer               │
│         (cli.py — Composition Root)     │
│  유일하게 모든 레이어를 import 가능       │
└────────────┬───────────────┬────────────┘
             │               │
             ▼               ▼
┌────────────────┐  ┌────────────────────┐
│ Application    │  │ Infrastructure     │
│ (Use Cases)    │  │ (Adapters)         │
│                │  │                    │
│ PublishPosts   │  │ GoogleSheetsRepo   │
│ ResetStuck     │  │ SeleniumAdapter    │
│                │  │ TistoryEditor      │
│                │  │ KakaoAuth          │
└───────┬────────┘  └────────┬───────────┘
        │                    │
        ▼                    ▼
┌──────────────────────────────────────────┐
│             Domain Layer                  │
│    (Entities, Value Objects, Ports)       │
│                                          │
│    Post Entity    PostStatus Enum        │
│    PostContent    PublishResult           │
│    PostRepository(ABC)  BrowserPort(ABC) │
│                                          │
│    ※ 외부 의존성 ZERO — 순수 Python      │
└──────────────────────────────────────────┘
```

**의존성 규칙**: Domain은 어떤 레이어도 import하지 않습니다. Infrastructure가 Domain의 Port 인터페이스를 구현하고, Interface(cli.py)에서 조립합니다.

### Post 상태 머신

```
대기 → 발행대기 → 발행중 → 발행완료
                    ↓
                 발행실패 → 발행대기 (재시도)
                    ↓
                 고스트 복구 → 발행대기
```

### LLM Provider 추상화

```
.env: LLM_PROVIDER=gemini (또는 claude)
         ↓
build_llm_request.js → 동적 URL/headers/body 생성
         ↓
HTTP Request (Generic) → LLM API 호출
         ↓
normalize_llm_response.js → 통합 텍스트 추출
```

워크플로우 JSON 수정 없이 `.env` 한 줄로 LLM 제공자를 전환할 수 있습니다.

## Google Sheets 스키마

Pipeline A/B가 공유하는 스프레드시트 컬럼 구조:

| 컬럼 | 내용 | Pipeline A 쓰기 | Pipeline B 읽기 |
|------|------|:---:|:---:|
| A: 키워드 | 검색 키워드 | | ✅ |
| B: 상태 | 대기/발행대기/발행중/발행완료/발행실패 | ✅ | ✅ |
| C: 제목 | 블로그 글 제목 | ✅ | ✅ |
| D: 본문 | 마크다운 콘텐츠 | ✅ | ✅ |
| E: 메타설명 | SEO 메타 디스크립션 | ✅ | ✅ |
| F: 카테고리 | 글 카테고리 | ✅ | ✅ |
| G: 태그 | 쉼표 구분 태그 | ✅ | ✅ |
| H: FAQ스키마 | JSON-LD 스키마 | ✅ | ✅ |
| I: 프롬프트유형 | A/B/C | ✅ | |
| J: Haiku검증 | 교차 검증 결과 | ✅ | |
| K: 발행URL | 발행된 글 URL | | ✅ |
| L: 생성일시 | 콘텐츠 생성 시각 | ✅ | |

## 트러블슈팅

### 카카오 로그인 2FA 반복 요구

첫 실행 시 수동으로 2FA 인증 후, 쿠키가 `.browser_data/`에 저장됩니다. 이후 자동 로그인됩니다.

```bash
# 첫 실행: 브라우저 표시 모드로 2FA 수동 인증
HEADLESS=false python -m src.interface.cli
```

### n8n 워크플로우 실행 실패

```bash
# Docker 상태 확인
docker-compose ps

# n8n 로그 확인
docker-compose logs --tail=50 n8n

# 최근 실행 이력 확인
./check_status.sh --detail
```

### Pipeline B 본문 누락

`tistory_editor.py`에서 마크다운 모드 전환 시 `window.confirm()` 팝업이 발생합니다. `window.confirm` 오버라이드로 처리됩니다. 문제 지속 시 `.browser_data/`를 삭제하고 재실행합니다.

```bash
rm -rf .browser_data/
HEADLESS=false python -m src.interface.cli
```

## 개발 가이드

### 커밋 컨벤션

```
feat(domain): add PostStatus value object
test(domain): add PostStatus transition tests
feat(infra): implement GoogleSheetsPostRepository
fix(domain): handle edge case in mark_failed truncation
refactor(app): simplify PublishPostsUseCase error handling
```

### 품질 게이트 기준

| 항목 | 기준 |
|------|------|
| 단위 테스트 커버리지 | 80% 이상 |
| 전체 테스트 통과율 | 100% |
| 린트 경고 (ruff) | 0건 |
| 타입 에러 (mypy) | 0건 |
| DDD 레이어 위반 | 0건 |

### 새 키워드 추가

Google Sheets에 행을 추가하고 A열(키워드)과 B열(상태=대기)을 입력하면, 다음 Pipeline A 실행 시 자동으로 콘텐츠가 생성됩니다.

## 관련 문서

| 문서 | 설명 |
|------|------|
| `masterplan_v2.3.md` | 전체 프로젝트 마스터 플랜 (Phase 1~7) |
| `prosess.md` | 개발 프로세스 추적 로그 |
| `SEO_SETUP_GUIDE.md` | Google Search Console, 네이버 서치어드바이저 등록 가이드 |
| `CLAUDE.md` | Claude Code 에이전트 설정 |

## 라이선스

Private Project — All Rights Reserved
