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

- **DDD 4-Layer 아키텍처**: Domain, Application, Infrastructure, Interface 계층 분리
- **TDD 기반 개발**: 431건 테스트, 커버리지 92%+
- **LLM Provider 추상화**: `.env`의 `LLM_PROVIDER` 값으로 Gemini/Claude 전환
- **3종 프롬프트 자동 라우팅**: 키워드 유형(용어/비교/에러해결)별 최적 프롬프트
- **Lenient JSON 파서**: LLM이 생성하는 비정형 JSON 자동 복구
- **4항목 교차 검증**: 정확성, 논리성, 완성도, 유용성을 별도 LLM으로 검증
- **FAQ JSON-LD 자동 주입**: Google 리치 스니펫 대응
- **고스트 복구**: 발행 중 장애 시 자동 상태 롤백

## 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.9+ |
| 아키텍처 | DDD 4-Layer (Hexagonal) |
| 워크플로우 엔진 | n8n 1.76.1 (Docker) |
| 브라우저 자동화 | SeleniumBase 4.25+ |
| 데이터 저장소 | Google Sheets (gspread) |
| LLM (콘텐츠 생성) | Gemini 2.0 Flash / Claude Sonnet 4.5 |
| LLM (교차 검증) | Claude Haiku |
| 검색 데이터 | SerpAPI |
| 린트/타입 체크 | ruff, mypy |
| 테스트 | pytest (431건, 커버리지 92%) |

## 디렉토리 구조

```
blog-automation/
├── src/                              # Python 소스 코드 (DDD 4-Layer)
│   ├── domain/                       # Layer 0: 핵심 비즈니스 로직 (외부 의존성 ZERO)
│   │   ├── entities/
│   │   │   └── post.py               #   Post 엔티티 + 상태 머신
│   │   ├── value_objects/             #   PostStatus, PostContent, PublishResult 등 (10개)
│   │   ├── ports/                     #   PostRepository, BrowserPort 등 인터페이스 (8개)
│   │   ├── services/                  #   PublishPolicy, QuotaManager 등 도메인 서비스 (8개)
│   │   └── exceptions.py             #   도메인 예외 계층
│   ├── application/                   # Layer 1: 유스케이스 (Domain만 의존)
│   │   ├── use_cases/                 #   Publish, Revise, CheckIndex 등 (11개)
│   │   ├── services/                  #   InternalLinkEnricher
│   │   └── dto.py                     #   PublishBatchResult DTO
│   ├── infrastructure/                # Layer 2: 외부 시스템 어댑터 (Port 구현)
│   │   ├── browser/                   #   Tistory 발행 모듈 (15개)
│   │   │   ├── tistory_editor.py      #     발행 오케스트레이터
│   │   │   ├── api_publisher.py       #     API 발행 + 재시도
│   │   │   ├── publish_verifier.py    #     발행 검증 + URL 추출
│   │   │   ├── content_injector.py    #     HTML 본문 주입
│   │   │   ├── form_filler.py         #     에디터 폼 필드 조작
│   │   │   ├── markdown_converter.py  #     Markdown → HTML
│   │   │   ├── html_transformer.py    #     lazy loading, nofollow, FAQ 스키마
│   │   │   ├── selenium_adapter.py    #     BrowserPort 구현체
│   │   │   ├── kakao_auth.py          #     카카오 로그인
│   │   │   └── dom_selectors.py       #     DOM 셀렉터 Fallback Chain
│   │   ├── persistence/               #   데이터 접근 (4개)
│   │   │   ├── google_sheets_repo.py  #     PostRepository → Google Sheets
│   │   │   ├── column_map.py          #     컬럼 매핑 (A~AH, 34열)
│   │   │   ├── in_memory_repo.py      #     테스트용 InMemory 구현
│   │   │   └── json_site_profile.py   #     SiteProfile JSON 어댑터
│   │   ├── seo/                       #   SEO 어댑터 (7개)
│   │   │   ├── indexing_checker.py    #     GSC 색인 확인
│   │   │   ├── indexing_submitter.py  #     Google Indexing API
│   │   │   ├── internal_linker.py     #     내부 링크 전략
│   │   │   └── html_optimizer.py      #     HTML 최적화
│   │   ├── notification/              #   알림 (Slack, Telegram, Null)
│   │   └── config.py                  #   환경 설정
│   └── interface/
│       └── cli.py                     # Layer 3: Composition Root (진입점)
│
├── n8n/                               # Pipeline A — 콘텐츠 생성
│   ├── workflow_complete.json         #   n8n 워크플로우 (22노드)
│   ├── prompts/                       #   LLM 프롬프트 (4종)
│   │   ├── prompt_a_terminology.md    #     용어 정의
│   │   ├── prompt_b_comparison.md     #     비교 분석
│   │   ├── prompt_c_troubleshooting.md#     에러 해결
│   │   └── prompt_d_verification.md   #     교차 검증
│   └── code_nodes/                    #   n8n JavaScript 노드 (11개)
│       ├── route_prompt.js            #     키워드 유형 판별
│       ├── build_llm_request.js       #     LLM 요청 빌더
│       ├── parse_json.js              #     Lenient JSON 파서
│       └── ...                        #     (8개 추가)
│
├── tests/                             # 테스트 (56파일, 431건)
│   ├── unit/                          #   단위 테스트
│   │   ├── domain/                    #     엔티티, VO, 서비스 (20+)
│   │   ├── application/               #     유스케이스 (10+)
│   │   └── infrastructure/            #     어댑터 (10+)
│   ├── integration/                   #   통합 테스트 (Google Sheets, 브라우저)
│   ├── e2e/                           #   E2E 테스트 (전체 발행 흐름)
│   └── fixtures/                      #   테스트 데이터
│
├── scripts/                           # 유틸리티 스크립트
│   ├── update_dashboard.py            #   성과 대시보드 자동 업데이트
│   └── add_keywords.py                #   키워드 일괄 추가
│
├── docs/                              # 문서
│   ├── EXECUTION_GUIDE.md             #   실행 방법 가이드
│   ├── SHEETS_GUIDE.md                #   Google Sheets 사용 가이드
│   └── superpowers/                   #   설계 문서 (plans + specs)
│
├── docker-compose.yml                 # n8n Docker 설정
├── Makefile                           # 빌드/테스트/품질 명령어
├── pyproject.toml                     # Python 패키지 설정
├── site_profile.json                  # 카테고리 매핑 + 키워드 분류
├── .env.example                       # 환경 변수 템플릿
├── run_pipeline_b.sh                  # Pipeline B cron 실행 스크립트
├── check_status.sh                    # 파이프라인 상태 모니터링
├── check_last_run.sh                  # 최근 실행 결과 확인
├── masterplan_v2.3.md                 # 마스터 플랜 (Phase 1~7)
└── process.md                         # 개발 프로세스 추적
```

## 빠른 시작

### 1. 설치

```bash
git clone <repository-url>
cd blog-automation
pip install -e ".[dev]"
docker compose up -d
```

### 2. 환경 변수

```bash
cp .env.example .env
# .env 파일에 KAKAO_ID, KAKAO_PW, TISTORY_BLOG, GOOGLE_CREDS 등 설정
```

### 3. 실행

```bash
# Pipeline B: 발행대기 글 자동 발행
python -m src.interface.cli

# Pipeline A: n8n 웹 UI에서 워크플로우 활성화
open http://localhost:5678
```

> 상세 설정은 [실행 방법 가이드](docs/EXECUTION_GUIDE.md) 참고

## CLI 명령어

```bash
python -m src.interface.cli                   # 기본 발행 (고스트 복구 → 발행 → CWV)
python -m src.interface.cli --revise          # 수정대기 글 업데이트
python -m src.interface.cli --check-index     # Google 색인 상태 점검
python -m src.interface.cli --submit-index    # Google Indexing API 제출
python -m src.interface.cli --generate-sitemap # sitemap.xml 생성
python -m src.interface.cli --status          # 블로그 현황 대시보드
python -m src.interface.cli --discover-keywords # GSC 키워드 발굴
python -m src.interface.cli --sync-categories  # 카테고리 동기화
python -m src.interface.cli --recover-failed   # 실패 글 일괄 복구
python -m src.interface.cli --publish-pages    # AdSense 필수 페이지 발행
```

## Google Sheets 구조

스프레드시트 `keyword_calendar_v2`에 5개 탭:

| 탭 | 용도 |
|----|------|
| **키워드 캘린더** | 전체 키워드 + 콘텐츠 + 발행 데이터 (34열) |
| **성과 대시보드** | 주간 KPI (Pipeline A/B + SEO 성과) |
| **키워드 피라미드** | 허브-스포크 내부 링크 설계 맵 |
| **파이프라인 로그** | 발행 이력 추적 |
| **사용 가이드** | 탭 설명 + QA 기준 |

키워드 캘린더 핵심 컬럼:

| 영역 | 열 | 내용 |
|------|-----|------|
| 기획 메타 | A~I | No, 키워드, 카테고리, 검색볼륨, 난이도, 우선순위, 예정일 |
| 상태 | J | 대기/발행대기/발행중/발행완료/발행실패/수정대기 |
| 생성 데이터 | K~P | 제목, 메타설명, 태그, FAQ스키마, 참고자료, 본문 |
| 발행/운영 | Q~Y | 발행URL, 발행일시, 색인여부, 에러, SERP, 검증결과 |
| 확장 운영 | Z~AH | 생성일시, 썸네일, 엔트리ID, CWV, 수정이력 |

> 상세 사용법은 [Google Sheets 사용 가이드](docs/SHEETS_GUIDE.md) 참고

## 아키텍처

### DDD 4-Layer + 의존성 역전

```
┌─────────────────────────────────────────┐
│           Interface Layer               │
│         (cli.py — Composition Root)     │
└────────────┬───────────────┬────────────┘
             │               │
             ▼               ▼
┌────────────────┐  ┌─────────────────────────┐
│ Application    │  │ Infrastructure          │
│ (Use Cases)    │  │ (Adapters)              │
│                │  │                         │
│ PublishPosts   │  │ GoogleSheetsRepo        │
│ ResetStuck     │  │ SeleniumAdapter         │
│ CheckIndexing  │  │ TistoryEditor (7모듈)   │
│ RevisePost     │  │ KakaoAuth              │
│ BatchRecover   │  │ CWV/Indexing/Sitemap   │
└───────┬────────┘  └────────┬────────────────┘
        │                    │
        ▼                    ▼
┌──────────────────────────────────────────┐
│             Domain Layer                  │
│    (Entities, Value Objects, Ports)       │
│    ※ 외부 의존성 ZERO — 순수 Python      │
└──────────────────────────────────────────┘
```

### Post 상태 머신

```
대기 → 발행대기 → 발행중 → 발행완료
                    ↓
                 발행실패 → 발행대기 (자동 복구)
                    ↓
                 수정대기 → 수정중 → 발행완료
```

## 테스트 & 품질

```bash
make test-unit      # 단위 테스트
make coverage       # 커버리지 (80%+ 필수)
make lint           # ruff 린트
make typecheck      # mypy 타입 체크
make validate-ddd   # DDD 레이어 규칙 검증
make quality        # 전체 품질 게이트
```

| 게이트 | 기준 |
|--------|------|
| 단위 테스트 | 100% pass |
| 커버리지 | domain+app ≥ 80% |
| 린트 (ruff) | 0 warnings |
| 타입 (mypy) | 0 errors |
| DDD 레이어 위반 | 0 violations |

## 문서 목록

| 문서 | 설명 |
|------|------|
| [실행 방법 가이드](docs/EXECUTION_GUIDE.md) | 설치, 실행, CLI, 자동화, 트러블슈팅 |
| [Google Sheets 가이드](docs/SHEETS_GUIDE.md) | 시트 구조, 컬럼 설명, 상태 흐름, 운영법 |
| [마스터 플랜](masterplan_v2.3.md) | Phase 1~7 전체 설계 |
| [SEO 설정 가이드](SEO_SETUP_GUIDE.md) | GSC, 네이버 서치어드바이저 등록 |
| [AdSense 페이지 가이드](ADSENSE_PAGES_GUIDE.md) | 필수 페이지 자동 발행 |
| [성과 대시보드](DASHBOARD.md) | 발행 현황, KPI |
| [프로젝트 리뷰](PROJECT_REVIEW.md) | 프로젝트 요약 |
| [개발 프로세스](process.md) | 개발 이력 추적 |
| [CLAUDE.md](CLAUDE.md) | Claude Code 에이전트 설정 |

## 라이선스

Private Project — All Rights Reserved
