# Project Review — B2B IT 블로그 자동화 시스템

> 키워드 입력부터 LLM 콘텐츠 생성, 교차 검증, 티스토리 자동 발행까지 전 과정을 자동화하는 풀스택 파이프라인. DDD 4-Layer 아키텍처와 TDD로 개발되었으며, 매일 새벽 콘텐츠를 생성하고 오전에 자동 발행하여 23건 이상의 블로그 글을 성공적으로 운영 중입니다.

---

## 아키텍처 개요

### DDD 4-Layer + Hexagonal Architecture

```
┌─────────────────────────────────────────────┐
│              Interface Layer                │
│          (cli.py — Composition Root)        │
│    유일하게 모든 레이어를 import 가능         │
└──────────┬──────────────────┬───────────────┘
           │                  │
           ▼                  ▼
┌──────────────────┐  ┌──────────────────────────┐
│ Application      │  │ Infrastructure            │
│ (Use Cases)      │  │ (Adapters)                │
│                  │  │                            │
│ PublishPosts     │  │ GoogleSheetsRepo           │
│ ResetStuck       │  │ SeleniumAdapter            │
│ CheckIndexing    │  │ KakaoAuth                  │
│ RevisePost       │  │ TistoryEditor (7모듈)      │
│ ClassifyCategory │  │  ├─ MarkdownConverter      │
│ SyncCategories   │  │  ├─ HtmlTransformer        │
│ CheckCWV         │  │  ├─ FormFiller             │
│ GenerateSitemap  │  │  ├─ ContentInjector        │
│                  │  │  ├─ ApiPublisher            │
│                  │  │  └─ PublishVerifier         │
└────────┬─────────┘  └──────────┬─────────────────┘
         │                       │
         ▼                       ▼
┌──────────────────────────────────────────────┐
│              Domain Layer                    │
│     (Entities, Value Objects, Ports)         │
│                                              │
│  Post Entity        PostStatus Enum          │
│  PostContent VO     PublishResult VO         │
│  SiteProfile VO     PublishingQuota VO       │
│  PostRepository(ABC)  BrowserPort(ABC)       │
│  InternalLinkService  PublishPolicy          │
│                                              │
│  ※ 외부 의존성 ZERO — 순수 Python stdlib    │
└──────────────────────────────────────────────┘
```

### 의존성 방향 규칙

| Layer | 경로 | Import 가능 | Import 불가 |
|-------|------|-------------|-------------|
| Domain | `src/domain/` | stdlib만 | Application, Infrastructure, 외부 패키지 |
| Application | `src/application/` | Domain | Infrastructure |
| Infrastructure | `src/infrastructure/` | Domain (Port 구현) | Application |
| Interface | `src/interface/cli.py` | 전체 (Composition Root) | — |

`make validate-ddd`로 계층 위반을 자동 검증하며, **Domain → Infrastructure import는 빌드 실패로 처리**됩니다.

### Port & Adapter 패턴

- **Ports** (Domain에 정의): `PostRepository`, `BrowserPort`, `SeoPort`, `SiteProfilePort` 등 ABC 인터페이스
- **Adapters** (Infrastructure에서 구현): `GoogleSheetsPostRepository`, `SeleniumBrowserAdapter`, `TistoryEditor` 등
- **Test Doubles**: `InMemoryPostRepository`, `MockBrowserAdapter`
- Use Cases는 생성자 주입(DI)으로 Port 인터페이스만 받음

---

## 기술적 하이라이트

### 1. tistory_editor 7-모듈 분할 (SRP)

1,892 LOC 단일 파일을 단일 책임 원칙에 따라 7개 모듈로 분할:

| 모듈 | 책임 |
|------|------|
| `tistory_editor.py` | 발행 오케스트레이터 (서브모듈 조율) |
| `markdown_converter.py` | 마크다운 → HTML 변환 (codehilite, tables, fenced_code) |
| `html_transformer.py` | lazy loading, nofollow, FAQ JSON-LD 스키마 주입 |
| `form_filler.py` | 에디터 폼 필드 조작 (제목, 설명, 슬러그) |
| `content_injector.py` | 본문/태그/카테고리 주입 (TinyMCE API) |
| `api_publisher.py` | Tistory 발행 API 호출 (Fetch + async script) |
| `publish_verifier.py` | 발행 검증, URL 추출, 비공개→공개 자동 복구 |

### 2. LLM Provider 추상화

`.env`의 `LLM_PROVIDER` 값 하나로 Gemini/Claude 전환. 워크플로우 JSON 수정 불필요:

```
.env: LLM_PROVIDER=gemini (또는 claude)
  → build_llm_request.js → 동적 URL/headers/body 생성
  → HTTP Request (Generic) → LLM API 호출
  → normalize_llm_response.js → 통합 텍스트 추출
```

### 3. 3종 프롬프트 자동 라우팅

키워드 유형에 따라 최적화된 프롬프트 자동 선택:

| 유형 | 프롬프트 | 예시 |
|------|----------|------|
| 용어 정의 | prompt_a_terminology | "Kubernetes란 무엇인가" |
| 비교 분석 | prompt_b_comparison | "Docker vs Podman 비교" |
| 에러 해결 | prompt_c_troubleshooting | "OOM Killer 원인과 해결" |

### 4. Lenient JSON 파서

LLM이 생성하는 비정형 JSON을 자동 복구하는 재귀 하강 파서:
- 이스케이프 안 된 따옴표 자동 처리
- 제어 문자 제거
- 불완전한 JSON 구조 복구
- `parse_json.js`에서 구현

### 5. 교차 검증 (5항목)

별도 LLM(Claude Haiku)으로 콘텐츠 품질 검증:
- 정확성 (accurate)
- 논리성 (logical)
- 완성도 (complete)
- 유용성 (useful)
- 심층성 (is_in_depth)
- quality_score ≥ 70 필수

---

## 품질 지표

| 항목 | 수치 | 검증 명령 |
|------|------|-----------|
| 단위 테스트 | **431건** 전체 통과 | `make test-unit` |
| ruff 경고 | **0건** | `make lint` |
| mypy 에러 | **0건** (91 files) | `make typecheck` |
| DDD 계층 위반 | **0건** | `make validate-ddd` |
| Domain+App 커버리지 | **80%+** | `make coverage` |

전체 품질 게이트 한번에 실행: `make quality`

---

## 운영 실적

| 항목 | 결과 |
|------|------|
| 자동 발행 성공 | **23건+** |
| 최신 발행 URL | /269 |
| FAQ JSON-LD 자동 주입 | 모든 발행 글에 적용 |
| Google AdSense | 승인 완료 |
| Google Analytics 4 | 설치 완료 (G-4Y6XE181NC) |
| Google Search Console | 등록 완료 |
| 네이버 서치어드바이저 | 등록 완료 |
| Pipeline A (콘텐츠 생성) | 매일 01:00 AM 자동 실행 |
| Pipeline B (발행) | 매일 09:00 AM 자동 실행 |

### Post 상태 머신

```
WAITING → GENERATING → PENDING → PUBLISHING → PUBLISHED
                                      ↓
                                    FAILED → (reset) → PENDING
```

Post 엔티티가 상태 전이 규칙을 직접 enforce. 잘못된 전이 시 `InvalidStateTransitionError` 발생.

---

## 주요 기술 스택

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
| 테스트 | pytest (431건) |
| CI/CD | Docker Compose + cron |

---

## 파일 구조 요약

### Domain Layer (`src/domain/`)
외부 의존성 ZERO. 순수 비즈니스 로직.

```
domain/
├── entities/post.py              # Post 엔티티 + 상태 머신
├── value_objects/                 # 14개 VO (PostStatus, PostContent, PublishResult 등)
├── ports/                        # 8개 Port ABC (PostRepository, BrowserPort 등)
├── services/                     # 8개 도메인 서비스 (PublishPolicy, InternalLinkService 등)
└── exceptions.py                 # 도메인 예외 계층
```

### Application Layer (`src/application/`)
Use Cases — Domain만 의존.

```
application/
├── use_cases/                    # 11개 UseCase
│   ├── publish_posts.py          # 발행 유스케이스
│   ├── reset_stuck_posts.py      # 고스트 복구
│   ├── revise_posts.py           # 미색인 재발행
│   ├── check_indexing.py         # GSC 색인 점검
│   ├── classify_category.py      # 카테고리 자동 분류
│   └── ...
├── services/
│   └── internal_link_enricher.py # 내부 링크 강화 서비스
└── dto.py                        # PublishBatchResult DTO
```

### Infrastructure Layer (`src/infrastructure/`)
Port 구현체. 외부 시스템 연동.

```
infrastructure/
├── browser/                      # 브라우저 자동화 (17개 모듈)
│   ├── tistory_editor.py         # 오케스트레이터
│   ├── markdown_converter.py     # MD → HTML
│   ├── html_transformer.py       # HTML 후처리
│   ├── form_filler.py            # 폼 필드
│   ├── content_injector.py       # 본문 주입
│   ├── api_publisher.py          # 발행 API
│   ├── publish_verifier.py       # 발행 검증
│   ├── kakao_auth.py             # 카카오 로그인
│   ├── selenium_adapter.py       # BrowserPort 구현
│   └── ...
├── persistence/                  # 데이터 저장소
│   ├── google_sheets_repo.py     # PostRepository 구현
│   └── in_memory_repo.py         # 테스트용
├── seo/                          # SEO 관련 어댑터
│   ├── indexing_checker.py       # GSC URL Inspection API
│   ├── internal_linker.py        # 내부 링크 삽입
│   └── ...
└── config.py                     # 환경 설정
```

### Pipeline A (`n8n/`)
n8n 워크플로우 기반 콘텐츠 자동 생성.

```
n8n/
├── workflow_complete.json        # 워크플로우 정의 (20+ 노드)
├── prompts/                      # LLM 프롬프트 (A/B/C + 검증)
└── code_nodes/                   # JavaScript 코드 노드 (10개)
```

---

## 개발 방법론

### TDD (Red → Green → Refactor)

Domain/Application 계층은 TDD로 개발:
1. **RED**: 실패하는 테스트 먼저 작성
2. **GREEN**: 테스트 통과하는 최소 코드
3. **REFACTOR**: 테스트 유지하며 정리
4. 각 사이클 = 별도 커밋

### DDD 계층 위반 자동 검증

`make validate-ddd`가 import 그래프를 분석하여 계층 규칙 위반을 빌드 타임에 차단:
- Domain → Infrastructure/Application import 시 즉시 실패
- Infrastructure → Application import 시 실패

### 커밋 컨벤션

```
feat(domain): add PostStatus value object
test(domain): add PostStatus transition tests
feat(infra): implement GoogleSheetsPostRepository
fix(domain): handle edge case in mark_failed truncation
refactor(app): simplify PublishPostsUseCase error handling
```

---

## 시스템 흐름

```
Pipeline A (n8n, 매일 01:00)          Pipeline B (Python, 매일 09:00)
┌──────────────────────┐              ┌──────────────────────────┐
│ Google Sheets 읽기   │              │ Google Sheets 읽기        │
│       ↓              │              │ (상태=발행대기)            │
│ SERP 검색 (SerpAPI)  │              │       ↓                  │
│       ↓              │              │ 카카오 로그인              │
│ 프롬프트 라우팅       │              │       ↓                  │
│ (용어/비교/에러해결)   │              │ TistoryEditor 발행        │
│       ↓              │              │  ├─ MD → HTML 변환        │
│ LLM 콘텐츠 생성      │              │  ├─ HTML 후처리           │
│ (Gemini/Claude)      │              │  ├─ 본문/태그/카테고리 주입 │
│       ↓              │              │  ├─ API 발행              │
│ JSON 파싱 + 복구     │              │  └─ 공개 검증 + 자동 복구  │
│       ↓              │              │       ↓                  │
│ 구조/중복 검증        │              │ Sheets 상태 업데이트       │
│       ↓              │              │ (발행완료 + URL 기록)      │
│ 교차 검증 (Haiku)    │              └──────────────────────────┘
│       ↓              │
│ Sheets 업데이트       │
│ (상태=발행대기)       │
└──────────────────────┘
```

Google Sheets가 두 파이프라인 간 버퍼/상태 저장소 역할을 수행합니다.
