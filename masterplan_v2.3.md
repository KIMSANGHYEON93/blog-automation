# B2B IT 블로그 자동화 마스터 플랜 v2.3

> **문서 버전**: v2.3 (DDD/TDD 아키텍처 적용 + 파이프라인 B 재설계)
> **최종 갱신**: 2026-02-28
> **아키텍처**: 비동기 듀얼 파이프라인 + DDD 4-Layer (Domain-Driven Design)
> **상세 프로세스**: `process.md` 참조 (1,207줄, DDD/TDD 개발 프로세스 전문)

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [시스템 아키텍처 (v2.3 DDD)](#2-시스템-아키텍처-v23-ddd)
3. [파이프라인 A: 콘텐츠 생성 및 검증](#3-파이프라인-a-콘텐츠-생성-및-검증)
4. [파이프라인 B: DDD 발행 워커](#4-파이프라인-b-ddd-발행-워커)
5. [Claude API 시스템 프롬프트 3종 (v2.2)](#5-claude-api-시스템-프롬프트-3종-v22)
6. [교차 검증 노드 프롬프트 (v2.2)](#6-교차-검증-노드-프롬프트-v22)
7. [Google Sheets 중간 버퍼 스키마](#7-google-sheets-중간-버퍼-스키마)
8. [5단계 구축 플랜 (v2.3 DDD 로드맵)](#8-5단계-구축-플랜-v23-ddd-로드맵)
9. [Phase별 체크리스트 (v2.3)](#9-phase별-체크리스트-v23)
10. [배포 및 운영 가이드 (v2.3)](#10-배포-및-운영-가이드-v23)
11. [마일스톤 게이트 및 KPI](#11-마일스톤-게이트-및-kpi)
12. [피벗 전략](#12-피벗-전략)
13. [의사결정 로그](#13-의사결정-로그)
14. [변경 이력](#14-변경-이력)

---

## 1. 프로젝트 개요

### 1.1 목표

B2B IT 인프라(Active Directory, Azure AD, SSO, 보안 솔루션) 도메인에서 기술 블로그를 자동 운영하여 12주 내 일 평균 유기적 유입 20명을 달성한다.

### 1.2 핵심 전략

| 구분 | 전략 |
|------|------|
| 콘텐츠 | 매스 트래픽(용어 정의) + 고CPC(에러 해결) 이중 구조 |
| SEO | 허브-스포크 내부 링크 + FAQ 리치 스니펫 + 데이터 시각화 차별화 |
| 자동화 | n8n 기반 생성 → Google Sheets 버퍼 → DDD 발행 워커 |
| 품질 보증 | 2-LLM 교차 검증 (Sonnet 생성 → Haiku 검증) |
| 코드 품질 | **DDD 4-Layer + TDD (테스트 커버리지 80%+)** |
| 수익화 | 애드센스 승인 후 고CPC 트러블슈팅 글로 수익 극대화 |

### 1.3 콘텐츠 분류 체계

| 유형 | 비중 | 자동화 수준 | 프롬프트 | 예시 |
|------|------|------------|---------|------|
| IT 기초 용어 | 40% | 100% 자동 | 프롬프트 A | "제로 트러스트란?", "SSO 작동 원리" |
| IT 트렌드/비교 | 35% | 100% 자동 | 프롬프트 B | "SAML vs OIDC", "온프레미스 vs 클라우드" |
| 실무 트러블슈팅 | 25% | 반자동 (수동 검수) | 프롬프트 C | "AADSTS50105 에러 해결", "AD FS 인증서 만료" |

---

## 2. 시스템 아키텍처 (v2.3 DDD)

### 2.1 아키텍처 진화 이력

| 버전 | 구조 | 문제점 | 결정 근거 |
|------|------|--------|----------|
| v1.0 | 모놀리식 7-Node 직렬 | SPOF, 장애 전파, 텍스트 유실 위험 | Gemini 비판 수용 |
| v2.1 | 듀얼 파이프라인 비동기 분리 | 프롬프트 스키마 불일치 3건 | Claude 검토 |
| v2.2 | 듀얼 파이프라인 + E2E 통합 테스트 | 파이프라인 B 모놀리식 553줄, 단위 테스트 불가 | Claude × Gemini 합의 |
| **v2.3** | **듀얼 파이프라인 + DDD 4-Layer + TDD** | - | **Claude DDD/TDD 설계** |

### 2.2 매크로 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────┐
│                  파이프라인 A (n8n Workflow)               │
│                   매일 01:00 AM 실행                      │
│                                                          │
│  [Node 1]          [Node 2]           [Node 3]           │
│  Schedule    →   Sheets Read    →    SerpAPI             │
│  Trigger          (Status=대기)       검색                │
│                                                          │
│  [Node 4]          [Node 5a/5b]       [Node 5c]          │
│  Claude API  →   URL+코드 기초   →   Haiku               │
│  (Sonnet)         스크리닝             검증(temp=0)       │
│                                                          │
│  [Node 6]                                                │
│  Sheets Update ─────────────────────────┐                │
│  (Status=발행대기)                       │                │
└──────────────────────────────────────────┼────────────────┘
                                           │
                              ┌─────────────▼──────────────┐
                              │    Google Sheets 버퍼       │
                              │    (중간 저장소)             │
                              └─────────────┬──────────────┘
                                           │
┌──────────────────────────────────────────┼────────────────┐
│           파이프라인 B (DDD Python Worker)                 │
│                매일 09:00 AM 실행                         │
│                                                          │
│  ┌─ Interface ──────────────────────────────────────┐    │
│  │  cli.py (Composition Root + 진입점)               │    │
│  └──────────────────────┬───────────────────────────┘    │
│                         │                                │
│  ┌─ Application ────────▼───────────────────────────┐    │
│  │  PublishPostsUseCase  │  ResetStuckPostsUseCase   │    │
│  └──────────┬───────────────────────┬───────────────┘    │
│             │                       │                    │
│  ┌─ Domain ─▼───────────────────────▼───────────────┐    │
│  │  Post(Entity)  PostStatus(VO)  Content(VO)        │    │
│  │  PostRepository(Port)  BrowserPort(Port)          │    │
│  └──────────┬───────────────────────┬───────────────┘    │
│             │                       │                    │
│  ┌─ Infra ──▼──────────┐  ┌────────▼───────────────┐    │
│  │ GoogleSheetsRepo     │  │ SeleniumBrowserAdapter  │    │
│  │ InMemoryRepo(Test)   │  │ MockBrowserAdapter(Test)│    │
│  └──────────────────────┘  └────────────────────────┘    │
└───────────────────────────────────────────────────────────┘
```

### 2.3 DDD 레이어 의존성 규칙

```
Interface → Application → Domain ← Infrastructure
                            ↑
                       의존성 역전(DIP)
```

| 규칙 | 설명 | 위반 시 |
|------|------|--------|
| **Domain은 순수** | Python 표준 라이브러리만 import 가능 | gspread, seleniumbase 등 외부 패키지 import 금지 |
| **Port는 Domain이 정의** | PostRepository, BrowserPort 인터페이스 | Infrastructure가 아닌 Domain 패키지에 위치 |
| **Infrastructure가 Port 구현** | GoogleSheetsRepo → PostRepository 구현 | Domain이 Infrastructure를 import하면 안 됨 |
| **Application이 조합** | Use Case가 Port를 통해 Domain과 Infra 연결 | 직접 Infrastructure 클래스를 참조하지 않음 |
| **Interface가 조립** | Composition Root에서 의존성 주입 | 유일하게 모든 레이어를 알고 있는 곳 |

### 2.4 아키텍처 설계 원칙 (v2.3 확장)

| 원칙 | 설명 | 적용 |
|------|------|------|
| 장애 격리 | 생성 실패와 발행 실패가 상호 독립 | 듀얼 파이프라인 분리 |
| 데이터 안전 | Claude 생성 텍스트를 즉시 저장 | Google Sheets 버퍼 |
| 자원 회수 | 브라우저 프로세스 완전 종료 | Cronjob 단발 실행 |
| Fail-fast | 환경 변수 누락 시 즉시 중단 | Config.validate() |
| Self-healing | 고스트 상태 자동 복구 | ResetStuckPostsUseCase |
| **의존성 역전** | **도메인이 인프라에 의존하지 않음** | **Port/Adapter 패턴** |
| **테스트 격리** | **외부 서비스 없이 핵심 로직 검증** | **InMemoryRepo + MockBrowser** |
| **상태 전이 보호** | **비즈니스 규칙을 Entity에 캡슐화** | **Post.mark_publishing() 등** |

### 2.5 바운디드 컨텍스트 맵

```
┌──────────────┐         ┌──────────────┐
│   Publishing  │◄─────── │   Content     │
│   Context     │ 읽기    │   Context     │
│  (Pipeline B) │         │  (Pipeline A) │
│               │         │               │
│  Post 발행    │         │  Post 생성    │
│  상태 관리    │         │  검증         │
└──────┬───────┘         └──────────────┘
       │
       │ 공유 커널 (Shared Kernel)
       ▼
┌──────────────┐
│   Shared      │
│   Kernel      │
│               │
│  PostStatus   │
│  시트 스키마  │
│  컬럼 매핑    │
└──────────────┘
```

---

## 3. 파이프라인 A: 콘텐츠 생성 및 검증

> **v2.3.1 (Phase 5.5) 업데이트**: 모델 업그레이드, SERP 구조화, 검증 확장, 본문 길이 검증 추가.

### 3.1 n8n 워크플로우 노드 명세

| Node | 유형 | 기능 | 입력 | 출력 |
|------|------|------|------|------|
| 1 | Schedule Trigger | 매일 01:00 AM 실행 | - | 트리거 신호 |
| 2 | Google Sheets Read | Status="대기" 행 읽기 | 시트 연결 | 키워드+메타데이터 |
| 3 | HTTP Request (SerpAPI) | Google 검색 스니펫 수집 | 키워드 | 상위 10개 스니펫 |
| **3b** | **Code Node (Parse SERP Data)** | **SERP 구조화 추출 (organic 7, PAA 5, related 8, KG)** | **SerpAPI 응답** | **구조화 SERP 텍스트** |
| 4 | Code Node (Route Prompt) | 프롬프트 A/B/C 분기 + SERP 데이터 결합 | 구조화 SERP + 시트 | Claude API 요청 |
| 5 | HTTP Request (Claude API) | 콘텐츠 생성 (**Sonnet 4.5, max_tokens 8192**) | 키워드+SERP+프롬프트 | JSON (제목/본문/메타/FAQ) |
| 6 | Code Node (Parse JSON) | JSON 파싱 + 필수 필드 검증 + **본문 길이 검증** | Claude 응답 | 파싱 결과 |
| **6b** | **Code Node (Validate Structure)** | **마크다운 구조 검증 (H2/테이블/코드블록/FAQ)** | **파싱 결과** | **구조 검증 결과** |
| 7a | Code Node | URL 정규식+형식 검증 | 검증된 본문 | 검증 결과 |
| 7b | Code Node | 코드 블록 기초 포맷 스크리닝 | 검증된 본문 | 검증 결과 |
| 7c | HTTP Request (Claude API) | **4항목 검증 (is_accurate/logical/complete/useful) + quality_score** (Haiku, temp=0) | 생성된 JSON | 통과/실패 판정 |
| 8 | Code Node (Parse Verification) | **4항목 판정 로직 + quality_score** | Haiku 응답 | 통과/실패 |
| 9 | IF Node | 검증 통과 분기 | 검증 결과 | 발행대기/검수필요 |
| 10a/b | Google Sheets Update | 결과 저장 (Status 변경) | 검증 결과+콘텐츠 | 발행대기/검수필요 |

### 3.2 Phase 5.5 변경 요약

| 변경 | 이전 | 이후 |
|------|------|------|
| 콘텐츠 생성 모델 | claude-3-haiku-20240307 | claude-sonnet-4-5-20250514 |
| max_tokens | 4096 | 8192 |
| SERP 데이터 | organic_results 5개 스니펫만 | organic 7 + PAA 5 + related 8 + KG |
| 프롬프트 분량 지시 | "2000자 이내" | "최소 1500/2000자 이상" |
| 프롬프트 섹션 요구 | 없음 | 섹션별 최소 글자 수 명시 |
| 본문 길이 검증 | 없음 | A: 1500자, B/C: 2000자 최소 |
| 마크다운 구조 검증 | 없음 | H2/테이블/코드블록/FAQ 카운트 |
| Haiku 검증 항목 | 2개 (is_accurate, is_logical) | 4개 (+is_complete, is_useful) + quality_score |
| IMAGE_PLACEHOLDER | `<!-- IMAGE_PLACEHOLDER -->` | "이미지 삽입 금지 (텍스트로만 설명)" |
| FAQ LD+JSON | 수동 처리 | Pipeline B에서 자동 주입 |

---

## 4. 파이프라인 B: DDD 발행 워커

### 4.1 v2.2 → v2.3 구조 변환

| 항목 | v2.2 (모놀리식) | v2.3 (DDD) |
|------|---------------|------------|
| 파일 수 | 1개 (553줄) | 20+ 파일 (레이어별 분리) |
| Post 표현 | `dict` (타입 안전성 없음) | `Post` Entity + `Content` VO |
| 상태 관리 | 문자열 비교 | `PostStatus` Enum + 전이 규칙 |
| Sheets 접근 | `SheetManager` (gspread 직접 의존) | `PostRepository` Port → `GoogleSheetsRepo` |
| 브라우저 제어 | `TistoryPublisher` (Selenium 직접 의존) | `BrowserPort` → `SeleniumBrowserAdapter` |
| 테스트 가능성 | 통합 테스트만 가능 | 단위 테스트 30+건 (Mock 기반) |
| 오케스트레이션 | `main()` 함수 | `PublishPostsUseCase` |

### 4.2 디렉토리 구조

```
blog-automation/
│
├── src/
│   ├── __init__.py
│   │
│   ├── domain/                          # ① 순수 비즈니스 로직 (외부 의존 0)
│   │   ├── __init__.py
│   │   ├── entities/
│   │   │   ├── __init__.py
│   │   │   └── post.py                  # Post 엔티티
│   │   ├── value_objects/
│   │   │   ├── __init__.py
│   │   │   ├── post_status.py           # PostStatus 열거형 (7개 상태)
│   │   │   ├── content.py               # Content (마크다운 본문 + 메타)
│   │   │   ├── publish_result.py        # PublishResult (성공/실패+URL)
│   │   │   └── credentials.py           # Credentials (인증 정보)
│   │   ├── ports/
│   │   │   ├── __init__.py
│   │   │   ├── post_repository.py       # PostRepository (ABC)
│   │   │   └── browser_port.py          # BrowserPort (ABC)
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   └── publish_policy.py        # 발행 정책 (도메인 서비스)
│   │   └── exceptions.py                # 도메인 예외 클래스
│   │
│   ├── application/                     # ② 유스케이스 오케스트레이션
│   │   ├── __init__.py
│   │   ├── use_cases/
│   │   │   ├── __init__.py
│   │   │   ├── publish_posts.py         # PublishPostsUseCase
│   │   │   └── reset_stuck_posts.py     # ResetStuckPostsUseCase
│   │   └── dto.py                       # Data Transfer Objects
│   │
│   ├── infrastructure/                  # ③ 외부 시스템 어댑터
│   │   ├── __init__.py
│   │   ├── persistence/
│   │   │   ├── __init__.py
│   │   │   ├── google_sheets_repo.py    # PostRepository 구현
│   │   │   ├── in_memory_repo.py        # 테스트용 InMemory 구현
│   │   │   └── column_map.py            # 시트 컬럼 매핑 상수
│   │   ├── browser/
│   │   │   ├── __init__.py
│   │   │   ├── selenium_adapter.py      # BrowserPort 구현
│   │   │   ├── kakao_auth.py            # 카카오 인증 모듈
│   │   │   ├── tistory_editor.py        # 에디터 조작 모듈
│   │   │   ├── dom_selectors.py         # 셀렉터 Fallback Chain
│   │   │   ├── js_injector.py           # safe_js_inject
│   │   │   ├── human_typing.py          # human_type
│   │   │   └── mock_browser.py          # 테스트용 Mock 구현
│   │   ├── config.py                    # Config + validate()
│   │   └── logging_setup.py             # 로깅 설정
│   │
│   └── interface/                       # ④ 진입점
│       ├── __init__.py
│       └── cli.py                       # Composition Root + main()
│
├── tests/
│   ├── unit/                            # 단위 테스트 (순수 로직)
│   │   ├── domain/
│   │   │   ├── test_post.py             # 상태 전이, 발행 가능성
│   │   │   ├── test_post_status.py      # 열거형 값, 전이 테이블
│   │   │   ├── test_content.py          # has_body(), fallback
│   │   │   ├── test_publish_result.py   # ok/fail 팩토리
│   │   │   └── test_publish_policy.py   # 발행 정책 규칙
│   │   └── application/
│   │       ├── test_publish_posts_usecase.py   # 핵심 시나리오 7+건
│   │       └── test_reset_stuck_usecase.py     # 고스트 복구 3+건
│   ├── integration/                     # 통합 테스트 (실제 서비스)
│   │   ├── test_google_sheets_repo.py
│   │   ├── test_selenium_adapter.py
│   │   └── test_js_injector.py
│   ├── e2e/                             # E2E 테스트
│   │   └── test_full_publish_flow.py
│   ├── fixtures/                        # 테스트 픽스처
│   │   ├── sample_post.json
│   │   ├── sample_markdown.md
│   │   └── sample_faq_schema.json
│   └── conftest.py                      # pytest 공통 픽스처
│
├── pyproject.toml
├── Makefile
├── .env.example
├── process.md                           # DDD/TDD 개발 프로세스 (1,207줄)
└── masterplan_v2.3.md                   # 본 문서
```

### 4.3 Domain Layer 핵심 설계

#### 4.3.1 Post 엔티티 — 상태 전이 규칙

Post 엔티티가 비즈니스 규칙을 캡슐화한다. 외부에서 `post.status = "발행완료"` 같은 직접 변경이 불가하고, 반드시 `mark_*()` 메서드를 통해 상태를 전이한다.

```python
# src/domain/entities/post.py

@dataclass
class Post:
    row_index: int                          # 식별자
    keyword: str
    category: str = ""
    content: Optional[Content] = None
    status: PostStatus = PostStatus.PENDING
    published_url: str = ""
    published_at: Optional[datetime] = None
    error_message: str = ""

    def mark_publishing(self) -> None:
        """발행대기 → 발행중 (규칙: PENDING만 전이 가능)"""
        if self.status != PostStatus.PENDING:
            raise InvalidStatusTransition(self.status, PostStatus.PUBLISHING)
        self.status = PostStatus.PUBLISHING

    def mark_published(self, url: str) -> None:
        """발행중 → 발행완료"""
        self.status = PostStatus.PUBLISHED
        self.published_url = url
        self.published_at = datetime.now()

    def mark_failed(self, reason: str) -> None:
        """발행중 → 발행실패 (사유 200자 절단)"""
        self.status = PostStatus.FAILED
        self.error_message = reason[:200]

    def reset_to_pending(self) -> None:
        """고스트 복구: 발행중 → 발행대기"""
        if self.status != PostStatus.PUBLISHING:
            return
        self.status = PostStatus.PENDING
        self.error_message = "이전 실행 중단으로 자동 복구됨"

    def is_publishable(self) -> bool:
        """발행 가능 여부 = 대기 상태 + 본문 존재"""
        return (
            self.status == PostStatus.PENDING
            and self.content is not None
            and self.content.has_body()
        )
```

#### 4.3.2 상태 전이도 (도메인 규칙)

```
                         ┌──────────────┐
                         │   Post 생성   │
                         │  (Pipeline A) │
                         └──────┬───────┘
                                │
    [사용자 입력]               ▼
        │              ┌──────────────┐
        ▼              │    대기       │
      대기 ───────────→│  (WAITING)   │
        │              └──────┬───────┘
        │                     │ Pipeline A 처리
        │              ┌──────▼───────┐
        │              │   생성중      │
        │              │ (GENERATING) │
        │              └──────┬───────┘
        │                     │
        │              ┌──────▼───────┐
        │              │   발행대기    │ ◄── is_publishable() 검증 지점
        │              │  (PENDING)   │
        │              └──────┬───────┘
        │                     │ mark_publishing()
        │              ┌──────▼───────┐
        │              │    발행중     │ ◄── 고스트 복구 대상
        │              │ (PUBLISHING) │
        │              └───┬──────┬───┘
        │                  │      │
        │      mark_published()  mark_failed()
        │                  │      │
        │           ┌──────▼─┐  ┌─▼──────────┐
        │           │ 발행완료│  │  발행실패   │
        │           │(PUBLISHED)│(FAILED)     │
        │           └────────┘  └─────────────┘
        │
        └──→ 보류 (HOLD)
```

#### 4.3.3 Port 인터페이스 (도메인이 정의)

```python
# src/domain/ports/post_repository.py
class PostRepository(ABC):
    @abstractmethod
    def find_pending(self, limit: int = 5) -> List[Post]: ...

    @abstractmethod
    def save(self, post: Post) -> None: ...

    @abstractmethod
    def find_stuck(self) -> List[Post]: ...


# src/domain/ports/browser_port.py
class BrowserPort(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def login(self) -> bool: ...

    @abstractmethod
    def publish(self, post: Post) -> PublishResult: ...
```

### 4.4 Application Layer — Use Case

```python
# src/application/use_cases/publish_posts.py
class PublishPostsUseCase:
    def __init__(self, repo: PostRepository, browser: BrowserPort, ...):
        self._repo = repo
        self._browser = browser

    def execute(self) -> PublishStats:
        posts = self._repo.find_pending(limit=self._max_posts)
        self._browser.start()
        try:
            if not self._browser.login():
                return stats  # 로그인 실패 → 중단
            for post in posts:
                self._publish_single(post, stats)
        finally:
            self._browser.stop()  # 항상 브라우저 종료
        return stats

    def _publish_single(self, post, stats):
        if not post.is_publishable():
            stats.skipped += 1
            return
        post.mark_publishing()
        self._repo.save(post)
        result = self._browser.publish(post)
        if result.success:
            post.mark_published(result.url)
        else:
            post.mark_failed(result.error)
        self._repo.save(post)
```

### 4.5 Infrastructure Layer — 어댑터 매핑

| v2.2 모놀리식 | v2.3 DDD | 레이어 |
|-------------|---------|--------|
| `Config` | `src/infrastructure/config.py` | Infra |
| `setup_logger()` | `src/infrastructure/logging_setup.py` | Infra |
| `COL / COL_EXT` | `src/infrastructure/persistence/column_map.py` | Infra |
| `SheetManager` | `src/infrastructure/persistence/google_sheets_repo.py` | Infra |
| - (신규) | `src/infrastructure/persistence/in_memory_repo.py` | Infra (Test) |
| `SELECTORS` | `src/infrastructure/browser/dom_selectors.py` | Infra |
| `find_element()` | `src/infrastructure/browser/dom_selectors.py` | Infra |
| `safe_js_inject()` | `src/infrastructure/browser/js_injector.py` | Infra |
| `human_type()` | `src/infrastructure/browser/human_typing.py` | Infra |
| `TistoryPublisher.login()` | `src/infrastructure/browser/kakao_auth.py` | Infra |
| `TistoryPublisher.publish_post()` | `src/infrastructure/browser/tistory_editor.py` | Infra |
| `TistoryPublisher` (전체) | `src/infrastructure/browser/selenium_adapter.py` | Infra |
| - (신규) | `src/infrastructure/browser/mock_browser.py` | Infra (Test) |
| `main()` | `src/interface/cli.py` | Interface |
| - (신규) | `src/domain/entities/post.py` | Domain |
| - (신규) | `src/domain/value_objects/*.py` | Domain |
| - (신규) | `src/domain/ports/*.py` | Domain |
| - (신규) | `src/application/use_cases/*.py` | Application |

### 4.6 테스트 피라미드

```
                    ╱╲
                   ╱  ╲
                  ╱ E2E╲           2건 (실제 티스토리)
                 ╱──────╲
                ╱        ╲
               ╱Integration╲       8건 (Sheets/Selenium)
              ╱────────────╲
             ╱              ╲
            ╱   Unit Tests   ╲     40건+ (순수 도메인+유스케이스)
           ╱──────────────────╲
```

| 계층 | 대상 | 건수 | 외부 의존 |
|------|------|------|----------|
| **Unit** | Post 엔티티, Value Objects, Use Cases | 40+ | 없음 (InMemoryRepo + FakeBrowser) |
| **Integration** | GoogleSheetsRepo, SeleniumAdapter, JsInjector | 8+ | Google Sheets, Chrome |
| **E2E** | 전체 발행 흐름, 고스트 복구 후 재발행 | 2+ | 전체 인프라 |

### 4.7 실행 흐름 (v2.3)

```
09:00 AM Cronjob → python -m src.interface.cli

  ┌─ Interface Layer ─────────────────────────────────────┐
  │  Config.validate()                                     │
  │  repo = GoogleSheetsPostRepository(...)                │
  │  browser = SeleniumBrowserAdapter(...)                  │
  └─────────────┬─────────────────────────────────────────┘
                │
  ┌─ Application Layer ──────────────────────────────────┐
  │  ResetStuckPostsUseCase(repo).execute()               │
  │    → repo.find_stuck() → post.reset_to_pending()      │
  │    → repo.save(post)                                   │
  │                                                        │
  │  PublishPostsUseCase(repo, browser).execute()          │
  │    → repo.find_pending()                               │
  │    → browser.start() → browser.login()                 │
  │    → for each post:                                    │
  │       post.mark_publishing() → repo.save()             │
  │       browser.publish(post) → PublishResult             │
  │       post.mark_published/failed() → repo.save()       │
  │       time.sleep(random 5~15분)                        │
  │    → browser.stop()                                    │
  └────────────────────────────────────────────────────────┘
```

---

## 5~7. 프롬프트 / 검증 / 시트 스키마

> **v2.3.1 (Phase 5.5) 업데이트**: 프롬프트 전면 재설계, 검증 4항목 확장.

### 5.1 프롬프트 섹션별 최소 요구사항 (Phase 5.5 신규)

**Prompt A (용어)**:

| 섹션 (H2) | 최소 | 필수 내용 |
|---|---|---|
| {키워드}란? | 200자 | 핵심 정의 + 부연 설명 |
| 작동 원리 | 400자 | 3~5단계, 기술적 세부사항 |
| 기업 환경 적용 사례 | 300자 | AD/Azure AD/AWS 시나리오 2~3개 |
| 장점과 한계 | 300자 | 마크다운 테이블 5행+ + 해석 |
| FAQ | 200자 | 3개, 각 답변 80자+ |

**Prompt B (비교)**:

| 섹션 (H2) | 최소 | 필수 내용 |
|---|---|---|
| 개요 | 200자 | 핵심 차이 3~4문장 |
| {기술A} 상세 | 400자 | 정의, 아키텍처, 기능 3+, 사용 사례 |
| {기술B} 상세 | 400자 | 정의, 아키텍처, 기능 3+, 사용 사례 |
| 상세 비교표 | — | 7행+ (보안/비용/확장성/관리/난이도/학습곡선/생태계) |
| 선택 가이드 | 300자 | SMB/Enterprise/스타트업별 추천 |
| FAQ | 200자 | 3개, 답변 80자+ |

**Prompt C (트러블슈팅)**:

| 섹션 (H2) | 최소 | 필수 내용 |
|---|---|---|
| 에러 현상 | 200자 | 에러 메시지 코드블록 + 발생 환경 |
| 원인 분석 | 450자 | H3로 원인 3+, 각 150자+, 빈도순 |
| 해결 방법 | 600자 | H3로 각 원인별, 코드블록 3+, 실행 전후 확인 |
| 예방 조치 | 300자 | 모니터링 스크립트, 자동화 팁 |
| FAQ | 200자 | 3개, 답변 80자+ |

### 5.2 검증 프롬프트 D (Phase 5.5 확장)

| 항목 | 설명 | 신규 |
|---|---|---|
| `is_accurate` | 기술 정확성 | 기존 |
| `is_logical` | 논리적 일관성 | 기존 |
| `is_complete` | H2 3개+, 필수요소(표/코드/FAQ) 존재 | **신규** |
| `is_useful` | 구체 사례/명령어, 기업 환경 적용 가능성 | **신규** |
| `quality_score` | 0~100점 (70점+ 양호) | **신규** |

### 5.3 스키마 변경 이력

| 항목 | v2.2 | v2.3 | v2.3.1 (Phase 5.5) |
|------|------|------|------|
| JSON 필드명 | `content` | `content` | 변경 없음 |
| 시트 컬럼 | A~S열 | A~S열 | 변경 없음 |
| 검증 항목 | 2개 | 2개 | **4개** + quality_score |
| 분량 지시 | "2000자 이내" | "2000자 이내" | **"최소 1500/2000자 이상"** |
| IMAGE_PLACEHOLDER | HTML 주석 | HTML 주석 | **"이미지 삽입 금지"** |

---

## 8. 5단계 구축 플랜 (v2.3 DDD 로드맵)

> **v2.3 변경**: v2.2의 4단계 → 5단계. Phase 2를 DDD 리팩토링으로 교체하고, 기존 Phase 2(파이프라인 B 단독 검증)를 Phase 2.5로 통합.
> **설계 원칙**: 병목 우선(역순 검증) + Inside-Out TDD (도메인 먼저, 인프라 나중)

### Phase 1: 기반 인프라 및 보안 환경 격리 (Week 1)

| # | 항목 | 상세 |
|---|------|------|
| 1.1 | 사내 보안 승인 | 기술 블로그 운영 고지서(1-Pager) 팀장 제출 → 승인 확보 |
| 1.2 | Google Workspace 세팅 | Cloud Console 프로젝트 → Sheets API 활성화 → 서비스 계정 JSON 키 |
| 1.3 | 중간 버퍼 시트 생성 | v2.2 스키마(A~S열) 구글 시트 → 서비스 계정에 편집자 권한 |
| 1.4 | 환경 변수 격리 | .env에 KAKAO_ID, KAKAO_PW, TISTORY_BLOG, API 키 저장 |
| 1.5 | **프로젝트 스캐폴딩** | **`blog-automation/` 디렉토리 구조 생성, pyproject.toml, Makefile** |
| 1.6 | **개발 도구 설치** | **pytest, ruff, mypy, pytest-cov** |

### Phase 2: DDD 리팩토링 + TDD (Week 1~2)

> ⚠️ **v2.3 신규**: Inside-Out TDD로 도메인부터 구축한 뒤, 인프라 어댑터를 붙이는 순서.

| # | 항목 | 상세 | TDD |
|---|------|------|-----|
| 2.1 | **Domain: Value Objects** | PostStatus, Content, PublishResult, Credentials | 🔴→🟢→🔵 |
| 2.2 | **Domain: Post Entity** | 상태 전이 규칙, is_publishable(), 고스트 복구 | 🔴→🟢→🔵 |
| 2.3 | **Domain: Port 인터페이스** | PostRepository(ABC), BrowserPort(ABC) | 정의만 |
| 2.4 | **Application: Use Cases** | PublishPostsUseCase, ResetStuckPostsUseCase | 🔴→🟢→🔵 (InMemoryRepo + FakeBrowser) |
| 2.5 | **Infra: InMemoryRepo** | 테스트용 저장소 구현 | Use Case 테스트에 사용 |
| 2.6 | **단위 테스트 전체 통과** | `make test-unit` → 40건+ 통과 | ✅ 커버리지 80%+ |

### Phase 2.5: 파이프라인 B 인프라 어댑터 + 단독 검증 (Week 2)

| # | 항목 | 상세 |
|---|------|------|
| 2.5.1 | **Infra: GoogleSheetsRepo** | PostRepository 구현, 컬럼 매핑 |
| 2.5.2 | **Infra: SeleniumBrowserAdapter** | BrowserPort 구현, 기존 로직 이식 |
| 2.5.3 | **Infra: 브라우저 모듈 분리** | kakao_auth, tistory_editor, dom_selectors, js_injector, human_typing |
| 2.5.4 | **Interface: cli.py** | Composition Root (의존성 조립) |
| 2.5.5 | 더미 데이터 주입 | 시트에 테스트 1건 (Status=발행대기) |
| 2.5.6 | HEADLESS=False 육안 검증 | 카카오 로그인 → 마크다운 주입 → 임시저장 |
| 2.5.7 | Self-Healing 테스트 | 강제 종료 → 재실행 → 고스트 복구 확인 |
| 2.5.8 | 통합 테스트 | `make test-integ` → 8건+ 통과 |

### Phase 3: 파이프라인 A 구축 (Week 2~3)

> v2.2와 동일.

| # | 항목 | 상세 |
|---|------|------|
| 3.1 | n8n 워크플로우 조립 | Sheets Read → SerpAPI → Claude Sonnet → Haiku → Sheets Update |
| 3.2 | 마스터 프롬프트 주입 | 프롬프트 A/B/C를 System Message에 세팅 |
| 3.3 | 교차 검증 로직 | Haiku 2항목(is_accurate, is_logical), Temperature=0 |
| 3.4 | JSON 파싱 에러 핸들링 | 실패 시 Status="검수필요" 분기 |
| 3.5 | 파이프라인 A 단독 테스트 | "대기" 키워드 → 수동 트리거 → "발행대기" 확인 |

### Phase 3.5: E2E 통합 테스트 (Week 3)

| # | 항목 | 상세 |
|---|------|------|
| 3.5.1 | 실제 데이터 생성 | 테스트 키워드 3건(용어+비교+에러) → n8n 수동 트리거 |
| 3.5.2 | **DDD 워커 연결 테스트** | **`python -m src.interface.cli` HEADLESS=False → 3건 발행/임시저장** |
| 3.5.3 | 렌더링 육안 검수 | 표, 코드 블록, contoso.com 마스킹 정상 출력 확인 |
| 3.5.4 | HTML/스키마 검증 | IMAGE_PLACEHOLDER 미노출 + LD+JSON FAQ 정상 확인 |
| 3.5.5 | 필드명 정합성 | 시트 P열이 `content` 값인지 확인 |
| 3.5.6 | **E2E 자동 테스트** | **`make test-e2e` → 2건 통과** |

### Phase 4: Go-Live (Week 4)

| # | 항목 | 상세 |
|---|------|------|
| 4.1 | 파이프라인 A 스케줄링 | n8n Schedule Trigger → 01:00 AM |
| 4.2 | **파이프라인 B 스케줄링** | **Cronjob → `python -m src.interface.cli` (09:00 AM, HEADLESS=true)** |
| 4.3 | 초기 색인 요청 | 첫 5건 Google Search Console URL 색인 요청 |
| 4.4 | 성과 대시보드 시작 | 매주 월요일 노출수/색인수/반려율 기록 |
| 4.5 | **레거시 코드 폐기** | **tistory_publisher.py → legacy/ 이동, 1주 병행 후 삭제** |

---

## 9. Phase별 체크리스트 (v2.3)

### 9.1 Phase 1: 기반 인프라

```
[ ] 1.1 팀장 보안 승인 (구두 또는 서면)
[ ] 1.2 Google Cloud Console 프로젝트 생성
[ ] 1.3 Google Sheets API 활성화
[ ] 1.4 서비스 계정 생성 + JSON 키 다운로드
[ ] 1.5 Google Sheets 시트 생성 (v2.2 스키마 A~S열)
[ ] 1.6 서비스 계정 이메일에 시트 편집자 권한 부여
[ ] 1.7 .env 파일 작성 (KAKAO_ID, KAKAO_PW, TISTORY_BLOG, GOOGLE_CREDS)
[ ] 1.8 Claude API 키 발급
[ ] 1.9 SerpAPI 키 발급
[ ] 1.10 .env 파일이 .gitignore에 포함 확인
[ ] 1.11 blog-automation/ 디렉토리 구조 생성 (섹션 4.2 참조)
[ ] 1.12 pyproject.toml 작성 (의존성 + pytest + ruff + mypy)
[ ] 1.13 Makefile 작성 (test-unit, test-integ, test-e2e, lint)
[ ] 1.14 python -m pytest --version 실행 확인
```

### 9.2 Phase 2: DDD 리팩토링 + TDD

```
[Domain: Value Objects]
[ ] 2.1a test_post_status.py → PostStatus 7개 열거형 값 테스트 통과
[ ] 2.1b test_content.py → has_body(), title_or_fallback() 테스트 통과
[ ] 2.1c test_publish_result.py → ok(), fail() 팩토리 테스트 통과

[Domain: Post Entity]
[ ] 2.2a test_post.py → mark_publishing() 정상 전이 테스트 통과
[ ] 2.2b test_post.py → 비정상 상태 전이 거부 테스트 통과
[ ] 2.2c test_post.py → mark_published() URL+시각 기록 테스트 통과
[ ] 2.2d test_post.py → mark_failed() 200자 절단 테스트 통과
[ ] 2.2e test_post.py → is_publishable() 4가지 조건 테스트 통과
[ ] 2.2f test_post.py → reset_to_pending() 고스트 복구 테스트 통과

[Domain: Ports]
[ ] 2.3a post_repository.py → ABC 인터페이스 정의 (find_pending, save, find_stuck)
[ ] 2.3b browser_port.py → ABC 인터페이스 정의 (start, stop, login, publish)

[Application: Use Cases]
[ ] 2.4a test_publish_posts_usecase.py → 정상 발행 테스트 통과
[ ] 2.4b test_publish_posts_usecase.py → 본문 없는 포스트 건너뛰기 테스트 통과
[ ] 2.4c test_publish_posts_usecase.py → 발행 실패 처리 테스트 통과
[ ] 2.4d test_publish_posts_usecase.py → 로그인 실패 시 중단 테스트 통과
[ ] 2.4e test_publish_posts_usecase.py → 예외 시 브라우저 종료 테스트 통과
[ ] 2.4f test_reset_stuck_usecase.py → 고스트 복구 테스트 통과
[ ] 2.4g test_reset_stuck_usecase.py → 빈 목록 처리 테스트 통과

[전체 검증]
[ ] 2.5 make test-unit → 전체 통과
[ ] 2.6 make test-cov → Domain+Application 커버리지 80%+
```

### 9.3 Phase 2.5: 인프라 어댑터 + 단독 검증

```
[인프라 구현]
[ ] 2.5.1 google_sheets_repo.py → PostRepository 구현 완료
[ ] 2.5.2 selenium_adapter.py → BrowserPort 구현 완료
[ ] 2.5.3 kakao_auth.py → 로그인 로직 분리 완료
[ ] 2.5.4 tistory_editor.py → 에디터 조작 로직 분리 완료
[ ] 2.5.5 dom_selectors.py → Fallback Chain 분리 완료
[ ] 2.5.6 js_injector.py → safe_js_inject 분리 완료
[ ] 2.5.7 cli.py → Composition Root 작성 완료

[단독 검증]
[ ] 2.5.8 시트에 더미 데이터 1건 입력 (Status=발행대기, content 필드 포함)
[ ] 2.5.9 python -m src.interface.cli (HEADLESS=False) → 카카오 로그인 성공
[ ] 2.5.10 마크다운 모드 전환 성공
[ ] 2.5.11 safe_js_inject() 본문 주입 성공
[ ] 2.5.12 임시저장 또는 비공개 발행 성공
[ ] 2.5.13 시트 Status "발행완료" 업데이트 확인
[ ] 2.5.14 Self-Healing: 강제 종료 후 '발행중'→'발행대기' 롤백 확인
[ ] 2.5.15 브라우저 프로세스 완전 종료 확인 (ps aux | grep chrome)
[ ] 2.5.16 make test-integ → 통합 테스트 8건+ 통과
```

### 9.4 Phase 3: 파이프라인 A 구축

```
[ ] 3.1 n8n 설치 (Docker 또는 Cloud)
[ ] 3.2 Google Sheets 자격 증명 연결
[ ] 3.3 Node 1: Schedule Trigger (01:00 AM)
[ ] 3.4 Node 2: Sheets Read → Status="대기" 필터
[ ] 3.5 Node 3: SerpAPI HTTP Request
[ ] 3.6 Node 3 → Code Node: 응답 파싱
[ ] 3.7 프롬프트 라우팅 Code Node (content_type 분기)
[ ] 3.8 Node 4: Claude Sonnet API 호출
[ ] 3.9 Node 4 → Code Node: JSON 파싱 (정규식 + 필드 검증)
[ ] 3.10 Node 5a: URL 검증 Code Node
[ ] 3.11 Node 5b: 코드 블록 lint Code Node
[ ] 3.12 Node 5c: Haiku 검증 (Temperature=0)
[ ] 3.13 Node 5c → Code Node: 방어 파싱
[ ] 3.14 Node 6: If Node (통과→발행대기, 실패→검수필요)
[ ] 3.15 Node 6: Sheets Update (O~S열 매핑)
[ ] 3.16 "대기" 키워드 1건 → 수동 트리거 → "발행대기" 확인
```

### 9.5 Phase 3.5: E2E 통합 테스트

```
[ ] 3.5.1 테스트 키워드 3건 입력 (용어 1, 비교 1, 에러 1)
[ ] 3.5.2 n8n 수동 트리거 → 3건 모두 "발행대기" 전이
[ ] 3.5.3 시트 O~S열 Claude 생성 데이터 정상 적재 확인
[ ] 3.5.4 P열 필드명 확인: "content" 값 (content_markdown 아님)
[ ] 3.5.5 python -m src.interface.cli (HEADLESS=False) → 3건 발행/임시저장
[ ] 3.5.6 마크다운 표(Table) 렌더링 정상
[ ] 3.5.7 코드 블록(```powershell) 렌더링 정상
[ ] 3.5.8 contoso.com 마스킹 확인
[ ] 3.5.9 <!-- IMAGE_PLACEHOLDER --> 독자 비노출 확인
[ ] 3.5.10 LD+JSON FAQ 스키마 정상 삽입 확인
[ ] 3.5.11 비교표 파이프 문자(|) 깨짐 없음
[ ] 3.5.12 시트 3건 모두 "발행완료" 확인
[ ] 3.5.13 make test-e2e → 2건 통과
```

### 9.6 Phase 4: Go-Live

```
[ ] 4.1 n8n Schedule Trigger 활성화 (01:00 AM)
[ ] 4.2 Cronjob 등록: python -m src.interface.cli (09:00 AM, HEADLESS=true)
[ ] 4.3 첫 자동 실행 후 시트 확인 (다음 날)
[ ] 4.4 발행 3건+ Google Search Console 색인 요청
[ ] 4.5 Google Analytics 추적 코드 삽입 확인
[ ] 4.6 성과 대시보드 W1 데이터 기록
[ ] 4.7 로그 파일 생성 확인 (/var/log/blog-publisher.log)
[ ] 4.8 2일 연속 자동 실행 성공 → 모니터링 주 1회 전환
[ ] 4.9 tistory_publisher.py → legacy/ 이동
[ ] 4.10 1주 병행 운영 후 레거시 삭제
```

### 9.7 DDD/TDD 아키텍처 정합성 체크리스트

```
[레이어 의존성 규칙]
[ ] Domain 레이어에 gspread, seleniumbase import 없음
[ ] Domain 레이어에 infrastructure import 없음
[ ] Application 레이어에 infrastructure import 없음
[ ] Application이 Domain Port만 참조 확인
[ ] Interface(cli.py)에서만 구체 클래스 조립 확인

[Port/Adapter 정합성]
[ ] PostRepository(ABC)의 메서드 = GoogleSheetsRepo 메서드 일치
[ ] BrowserPort(ABC)의 메서드 = SeleniumBrowserAdapter 메서드 일치
[ ] InMemoryRepo → PostRepository 구현 확인
[ ] MockBrowser → BrowserPort 구현 확인

[테스트 커버리지]
[ ] make test-unit → 전체 통과
[ ] Domain + Application 커버리지 80%+
[ ] make lint → ruff + mypy 경고 0건

[프롬프트 정합성 (v2.2 계승)]
[ ] 3개 프롬프트 모두 "content" 필드 (content_markdown 아님)
[ ] 3개 프롬프트 모두 "references" 필드 존재
[ ] 3개 프롬프트 모두 "internal_link_keywords" 필드 존재
[ ] 검증 프롬프트 D: "is_code_valid" 없음 (2항목만)
[ ] 구글 시트 P열 = Domain Content.body_markdown
[ ] 구글 시트 S열 = internal_link_keywords
```

---

## 10. 배포 및 운영 가이드 (v2.3)

### 10.1 서버 요구사항

| 항목 | 최소 사양 | 권장 사양 |
|------|----------|----------|
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |
| RAM | 2GB | 4GB |
| CPU | 1 vCPU | 2 vCPU |
| 디스크 | 20GB SSD | 40GB SSD |
| n8n | v1.20+ | 최신 안정 버전 |
| Python | 3.10+ | 3.11+ |

### 10.2 환경 변수

```bash
# .env
KAKAO_ID=your_kakao_email@example.com
KAKAO_PW=your_password
TISTORY_BLOG=your-blog-name
GOOGLE_CREDS=/path/to/credentials.json
SHEET_NAME=keyword_calendar_v2
MAX_POSTS=5
HEADLESS=true
MIN_DELAY=300
MAX_DELAY=900

# n8n
CLAUDE_API_KEY=sk-ant-api03-...
SERPAPI_KEY=your_serpapi_key
```

### 10.3 Cronjob (v2.3 변경)

```crontab
# v2.2 (폐기 예정)
# 0 9 * * * cd /opt/blog-automation && /usr/bin/python3 tistory_publisher.py >> /var/log/blog-publisher.log 2>&1

# v2.3 (DDD 진입점)
0 9 * * * cd /opt/blog-automation && /usr/bin/python3 -m src.interface.cli >> /var/log/blog-publisher.log 2>&1
```

### 10.4 개발 명령어 (Makefile)

```makefile
.PHONY: test test-unit test-integ test-e2e test-cov lint install

install:                              ## 의존성 설치
	pip install -e ".[dev]"

test-unit:                            ## 단위 테스트
	pytest tests/unit/ -v --tb=short

test-integ:                           ## 통합 테스트
	pytest tests/integration/ -v -m integration

test-e2e:                             ## E2E 테스트
	HEADLESS=false pytest tests/e2e/ -v -m e2e

test:                                 ## 전체 테스트
	pytest tests/ -v --tb=short

test-cov:                             ## 커버리지 측정
	pytest tests/unit/ --cov=src/domain --cov=src/application --cov-report=term-missing

lint:                                 ## 코드 품질
	ruff check src/ tests/
	mypy src/ --ignore-missing-imports
```

---

## 11. 마일스톤 게이트 및 KPI

### 11.1 12주 로드맵 (v2.3 수정)

| 주차 | 목표 | Go/No-Go 기준 | 실패 시 |
|------|------|---------------|--------|
| W1 | **인프라 + DDD 도메인 TDD** | **단위 테스트 40건+ 통과** | **설계 재검토** |
| W2 | **인프라 어댑터 + 파이프라인 B 검증** | **통합 테스트 8건+ 통과** | **어댑터 디버깅** |
| W2~3 | 파이프라인 A 구축 + 첫 5건 | 5건 색인 확인 | 기술 점검 |
| W3~4 | 주 3~5건 안정화 | 검증 통과율 80%+ | 프롬프트 튜닝 |
| W5~6 | 20건 누적 + SEO | CTR 1%+ | 제목/메타 AB |
| **W7~8** | **노출 500 + 색인 10** | **미달 시 피벗 검토** | **피벗 발동** |
| W9~10 | 애드센스 신청 | 승인 여부 | 품질 재검토 |
| **W11~12** | **일 유입 20명** | **미달 시 피벗 실행** | **피벗 실행** |

### 11.2 KPI (v2.3 추가)

| KPI | 도구 | 목표 | 주기 |
|-----|------|------|------|
| 발행 글 수 | Sheets | W4: 15, W8: 30 | 주간 |
| 색인 글 수 | Search Console | W8: 10+ | 주간 |
| 총 노출수 | Search Console | W8: 500+ | 주간 |
| 평균 CTR | Search Console | W12: 2%+ | 주간 |
| 일 유입 | Analytics | W12: 20+ | 일간 |
| 자동 발행률 | Sheets | 80%+ | 주간 |
| 검증 통과율 | 로그 | 85%+ | 주간 |
| **단위 테스트 통과율** | **pytest** | **100%** | **커밋마다** |
| **Domain+App 커버리지** | **pytest-cov** | **80%+** | **주간** |
| **lint 경고** | **ruff+mypy** | **0건** | **커밋마다** |

---

## 12. 피벗 전략

> v2.2와 동일.

| 단계 | 트리거 | 액션 |
|------|--------|------|
| **레벨 1** | W8 색인 10건 미달 | 키워드 하향, 롱테일 집중, 제목/메타 교체 |
| **레벨 2** | W10 CTR 1% 미달 | Matplotlib 차트 전 글 삽입, 원본 데이터 공개 |
| **레벨 3** | W12 일 유입 10명 미달 | 워드프레스 전환 (REST API, 301 리다이렉트) |

---

## 13. 의사결정 로그

| 일자 | 결정 사항 | 근거 | 제안자 |
|------|----------|------|--------|
| 2026-02-27 | 모놀리식 → 듀얼 파이프라인 | SPOF 제거, 장애 격리 | Gemini 제안, Claude 수용 |
| 2026-02-27 | HTTP HEAD → 정규식+DNS | 403 반환 문제 | Gemini 비판, Claude 수용 |
| 2026-02-27 | Flask → Cronjob | 좀비 프로세스 방지 | Gemini 제안, Claude 수용 |
| 2026-02-27 | 코드 검증 역할 재정의 | 정규식=lint, 문법=LLM | Claude 반박, Gemini 수용 |
| 2026-02-28 | 1회 로그인 | 반복 로그인→봇 탐지 | Claude 지적 |
| 2026-02-28 | json.dumps() JS 주입 | f-string XSS 위험 | Claude 지적 |
| 2026-02-28 | Config.validate() | IP 차단 방지 | Claude 설계 |
| 2026-02-28 | safe_reset_stuck_posts() | 고스트 방지 | Claude 설계, Gemini 수용 |
| 2026-02-28 | JSON 출력 강제 | API 텍스트 혼입 방어 | Claude 보완 |
| 2026-02-28 | "자체 검증" 제거 | 자기 확증 편향 | Claude 보완 |
| 2026-02-28 | FAQ 스키마 명시 | 리치 스니펫 규격 | Claude 보완 |
| 2026-02-28 | 티스토리 Open API 종료 | 2024.02 폐쇄 확인 | Claude 사실 확인 |
| 2026-02-28 | Gemini v2.2 교정 5건 | references/internal_link_keywords 복원 등 | Claude 검토, Gemini 교정 |
| 2026-02-28 | 잔존 3건 추가 교정 | content 필드명 통일, 120~155자, 상세도 | Claude 교정 |
| **2026-02-28** | **파이프라인 B DDD 4-Layer 전환** | **모놀리식 553줄 단위 테스트 불가, 강결합, 도메인 부재** | **Claude 설계** |
| **2026-02-28** | **TDD Inside-Out 방식 채택** | **도메인 먼저, 인프라 나중 — 비즈니스 규칙 우선 검증** | **Claude 설계** |
| **2026-02-28** | **Port/Adapter 패턴 적용** | **의존성 역전으로 InMemoryRepo+MockBrowser 테스트 가능** | **Claude 설계** |
| **2026-02-28** | **Composition Root를 cli.py에 집중** | **유일하게 구체 클래스를 아는 지점 — 교체 용이** | **Claude 설계** |
| **2026-02-28** | **레거시 병행 운영 후 폐기** | **1주 병행으로 무중단 전환** | **Claude 설계** |
| **2026-02-28** | **kakao_auth: hostname 기반 URL 판별** | **OAuth redirect URL query param false positive 수정** | **Claude 버그 수정** |
| **2026-02-28** | **kakao_auth: URL 안정화 폴링 (15초)** | **고정 sleep 3초 → 리다이렉트 완료 대기 폴링** | **Claude 버그 수정** |
| **2026-02-28** | **cli.py: user_data_dir 쿠키 영속화** | **매 실행 2FA 재요구 방지, test_login.py와 동작 일치** | **Claude 버그 수정** |
| **2026-02-28** | **Haiku→Sonnet 4.5 콘텐츠 생성 모델 변경** | **Haiku로 생성 시 본문 495~1,282자 — 목표 미달** | **Phase 5.5 품질 강화** |
| **2026-02-28** | **"2000자 이내" → "최소 N자 이상" 변경** | **상한 지시가 모델의 짧은 출력을 유도** | **Phase 5.5 품질 강화** |
| **2026-02-28** | **SERP 구조화 파싱 (Parse SERP Data 노드)** | **organic 5개 스니펫만으로 PAA/관련검색/KG 미활용** | **Phase 5.5 품질 강화** |
| **2026-02-28** | **검증 4항목 확장 (is_complete, is_useful)** | **짧고 피상적 콘텐츠가 2항목 검증 통과** | **Phase 5.5 품질 강화** |
| **2026-02-28** | **본문 길이 검증 추가 (parse_json.js)** | **495자 본문도 통과하는 문제 — 최소 길이 강제** | **Phase 5.5 품질 강화** |

---

## 14. 변경 이력

### 14.1 v2.1→v2.2 Gemini 교정 (5건)

| # | 결함 | 교정 | 상태 |
|---|------|------|------|
| 1 | 프롬프트 A/B `references` 누락 | 3개 프롬프트 모두 추가 | ✅ |
| 2 | `internal_link_keywords` 전체 누락 | 3개 프롬프트 + 시트 S열 추가 | ✅ |
| 3 | `is_code_valid` 합의 위반 | 2항목으로 복원 | ✅ |
| 4 | E2E 통합 테스트 누락 | Phase 3.5 삽입 | ✅ |
| 5 | 플레이스홀더 `[이곳에...]` 형식 | HTML 주석으로 통일 | ✅ |

### 14.2 v2.1→v2.2 잔존 이슈 (3건)

| # | 이슈 | 교정 | 상태 |
|---|------|------|------|
| 6 | `content_markdown` vs `content` 불일치 | `content`로 통일 | ✅ |
| 7 | meta_description "150자" vs "120~155자" | 전 프롬프트 "120~155자" | ✅ |
| 8 | Gemini 프롬프트 상세도 부족 | v2.1 상세 본문 유지 | ✅ |

### 14.3 Phase 2.5 카카오 로그인 버그 수정 (3건, 2026-02-28)

| # | 변경 | 파일 | 상세 |
|---|------|------|------|
| 20 | `_is_tistory_logged_in()` hostname 기반 판별 | `kakao_auth.py` | `urlparse`로 host만 검사, OAuth redirect URL false positive 수정 |
| 21 | 카카오 버튼 클릭 후 URL 안정화 폴링 | `kakao_auth.py` | `time.sleep(3)` → 최대 15초 폴링, accounts.kakao 체크 우선 |
| 22 | `cli.py`에 `user_data_dir` 전달 | `cli.py` | `.browser_data` 쿠키 영속화, 2FA 1회만 필요 |

### 14.4 v2.2→v2.3 DDD/TDD 아키텍처 적용 (11건)

| # | 변경 | 상세 | 영향 범위 |
|---|------|------|----------|
| 9 | 아키텍처 진화 이력 v2.3 추가 | 섹션 2.1 | 아키텍처 |
| 10 | 매크로 다이어그램에 DDD 4-Layer 반영 | 섹션 2.2 | 아키텍처 |
| 11 | DDD 레이어 의존성 규칙 섹션 신규 | 섹션 2.3 | 아키텍처 |
| 12 | 설계 원칙 3건 추가 (의존성 역전, 테스트 격리, 상태 전이 보호) | 섹션 2.4 | 아키텍처 |
| 13 | 바운디드 컨텍스트 맵 신규 | 섹션 2.5 | 아키텍처 |
| 14 | 파이프라인 B 전면 재설계 (DDD 구조) | 섹션 4 전체 | 파이프라인 B |
| 15 | 4단계 → 5단계 구축 플랜 (Phase 2 DDD, Phase 2.5 인프라) | 섹션 8 | 구축 플랜 |
| 16 | Phase 2/2.5 체크리스트 신규 (TDD 항목 포함) | 섹션 9.2~9.3 | 체크리스트 |
| 17 | DDD 아키텍처 정합성 체크리스트 신규 | 섹션 9.7 | 체크리스트 |
| 18 | Cronjob 진입점 변경 (cli.py) | 섹션 10.3 | 운영 |
| 19 | KPI 3건 추가 (테스트 통과율, 커버리지, lint) | 섹션 11.2 | KPI |

---

## 부록: 파일 산출물 목록

| 파일명 | 유형 | 버전 | 설명 |
|--------|------|------|------|
| `masterplan_v2.3.md` | 마크다운 | **v2.3** | 본 문서 (DDD 아키텍처 반영) |
| `process.md` | 마크다운 | v1.0 | DDD/TDD 개발 프로세스 (1,207줄, 코드 전문 포함) |
| `masterplan_v2.2.md` | 마크다운 | v2.2 | 이전 버전 (프롬프트/검증/시트 스키마 전문 참조) |
| `tistory_publisher.py` | Python | v1.0 (레거시) | 모놀리식 파이프라인 B (553줄, Phase 4에서 폐기) |
| `blog-automation/src/` | Python | v2.3 | DDD 4-Layer 파이프라인 B (20+ 파일) |
| `blog-automation/tests/` | Python | v2.3 | 테스트 스위트 (unit+integration+e2e, 50+건) |
| `keyword_calendar_v2.xlsx` | Excel | v2.0 | 키워드 캘린더 템플릿 |

---

> **현재 상태**: Phase 5.5 콘텐츠 품질 강화 완료 (2026-02-28). 75 tests passed / 커버리지 92.05% / ruff 0 / mypy 0
> 30개 B2B IT 키워드 투입 완료, Pipeline A (Sonnet 4.5, 01:00 AM) + Pipeline B (09:00 AM) 자동 운영 중
>
> **다음 단계**: Phase 5 — 운영 안정화 + SEO 기반 구축
> 상세 진행 추적: `process.md` 참조

---

## 15. Phase 5~7: 운영 로드맵 (Go-Live 이후)

### Phase 5.5: 콘텐츠 품질 강화 (2026-02-28)

> E2E 테스트 결과 본문 품질 미달 확인 → 근본 원인 5가지 해결.

| # | 항목 | 상세 |
|---|------|------|
| 5.5.1 | 모델 업그레이드 | Haiku → Sonnet 4.5, max_tokens 4096 → 8192 |
| 5.5.2 | 프롬프트 A/B/C 재설계 | 섹션별 최소 글자 수 명시, "2000자 이내" → "최소 N자 이상" |
| 5.5.3 | SERP 데이터 구조화 | Parse SERP Data 노드 추가 (organic 7 + PAA 5 + related 8 + KG) |
| 5.5.4 | 본문 길이 검증 | parse_json.js에 A: 1500, B/C: 2000 최소 검증 |
| 5.5.5 | 마크다운 구조 검증 | validate_structure.js 신규 (H2/테이블/코드블록/FAQ) |
| 5.5.6 | 검증 4항목 확장 | is_complete, is_useful, quality_score 추가 |
| 5.5.7 | IMAGE_PLACEHOLDER 제거 | "텍스트로만 설명" 지시로 변경 |
| 5.5.8 | FAQ LD+JSON 자동 주입 | PostContent.faq_ld_json() + tistory_editor.py |
| 5.5.9 | 내부 링크 키워드 굵게 | 프롬프트에 **굵게** 처리 지시 추가 |

### Phase 5: 운영 안정화 + SEO 기반 구축 (W1~2, ~2026-03-14)

> Go-Live 직후. 자동 파이프라인이 안정적으로 작동하는지 확인하고, 검색엔진 등록을 완료한다.

| # | 항목 | 상세 | 게이트 |
|---|------|------|--------|
| 5.1 | 자동 실행 모니터링 | Pipeline A(01:00)→B(09:00) 2일 연속 성공 확인 | 2일 연속 실행 로그 정상 |
| 5.2 | 로그 점검 체계 구축 | `/var/log/blog-publisher.log` 일일 점검 → 주 1회 전환 | 에러율 < 10% |
| 5.3 | Google Search Console 등록 | 사이트 소유권 확인 + sitemap.xml 제출 | 소유권 인증 완료 |
| 5.4 | Google Analytics 4 설치 | 추적 코드 삽입 + 실시간 유입 확인 | 실시간 보고서 동작 |
| 5.5 | 네이버 서치어드바이저 등록 | 사이트 등록 + robots.txt 크롤러 허용 확인 | 등록 승인 |
| 5.6 | 첫 5건 수동 색인 요청 | Search Console URL 검사 → 색인 요청 | 5건 색인 확인 |
| 5.7 | 성과 대시보드 시작 | 주간 KPI 기록 (노출수/색인수/반려율/발행수) | W1 데이터 기록 |
| 5.8 | 발행 품질 검수 | 첫 5건 렌더링 육안 확인 (표/코드블록/FAQ 스키마) | 결함 0건 |
| 5.9 | 레거시 코드 완전 폐기 | `legacy/` 디렉토리 삭제 (1주 병행 운영 후) | legacy/ 삭제 완료 |

### Phase 6: 콘텐츠 누적 + SEO 최적화 (W3~6, ~2026-04-11)

> 안정 발행을 유지하면서 SEO 최적화로 검색 노출을 끌어올린다.

| # | 항목 | 상세 | 게이트 |
|---|------|------|--------|
| 6.1 | 주 3~5건 안정 발행 | 자동 발행률 80%+ 유지, 검증 통과율 85%+ | 주간 발행 3건+ |
| 6.2 | 프롬프트 튜닝 | 검수필요 비율 > 20% 시 프롬프트 A/B/C 조정 | 통과율 85%+ |
| 6.3 | 내부 링크 구조 강화 | 허브-스포크 모델: 허브 글 3개 + 스포크 연결 | 글당 내부링크 3~5개 |
| 6.4 | FAQ 리치 스니펫 확인 | Search Console 리치결과 보고서에서 FAQ 노출 확인 | FAQ 색인 1건+ |
| 6.5 | 20건 누적 | 총 발행 글 20건 달성 | W4: 15건, W6: 20건 |
| 6.6 | 제목/메타 A/B 테스트 | CTR 저조 글 → 제목 교체 후 2주 비교 | CTR 개선 확인 |
| 6.7 | 반응형 스킨 최적화 | 모바일 페이지 속도 / Core Web Vitals 점검 | LCP < 2.5s |
| 6.8 | 카테고리 정비 | 3~5개 카테고리 균등 배분 확인 | 카테고리당 4건+ |

### Phase 7: 성장 + 수익화 (W7~12, ~2026-05-23)

> 색인과 노출이 궤도에 오르면 애드센스 승인을 신청하고, 수익화 체계를 구축한다.

| # | 항목 | 상세 | Go/No-Go |
|---|------|------|----------|
| 7.1 | W7~8 게이트 | 총 노출 500+ / 색인 10건+ | **미달 시 → 피벗 레벨 1** |
| 7.2 | 애드센스 승인 신청 | 필수 페이지 확인 (소개/개인정보/문의) + 20건+ 글 | W9~10 |
| 7.3 | 광고 배치 최적화 | 수동 광고 3~4개 전략 배치 (H2 위/중간/결론 앞) | 클릭율 측정 |
| 7.4 | 고CPC 키워드 집중 | 에러 해결(트러블슈팅) 글 비중 확대 | CPC > 1,000원 |
| 7.5 | W11~12 게이트 | 일 평균 유기적 유입 20명 | **미달 시 → 피벗 레벨 2~3** |
| 7.6 | CPA 제휴 검토 | 리더스CPA/애드팟 보험 상담 DB 연동 가능성 | 수익 다각화 판단 |
| 7.7 | 워드프레스 전환 검토 | 피벗 레벨 3 트리거 시 커스텀 도메인 + WP 이전 | 트래픽 부진 시 |

### Phase 5.5 체크리스트: 콘텐츠 품질 강화

```
[모델 + 길이 검증]
[x] 5.5.1 Claude 모델 claude-3-haiku → claude-sonnet-4-5-20250514 변경
[x] 5.5.2 max_tokens 4096 → 8192 변경
[x] 5.5.3 parse_json.js 본문 길이 검증 (A: 1500, B/C: 2000)

[프롬프트 재설계]
[x] 5.5.4 prompt_a_terminology.md 섹션별 최소 요구사항 추가
[x] 5.5.5 prompt_b_comparison.md 섹션별 최소 요구사항 추가
[x] 5.5.6 prompt_c_troubleshooting.md 섹션별 최소 요구사항 추가
[x] 5.5.7 "2000자 이내" → "최소 N자 이상" 변경
[x] 5.5.8 IMAGE_PLACEHOLDER → "이미지 삽입 금지 (텍스트로만 설명)"
[x] 5.5.9 internal_link_keywords 굵게 처리 지시 추가

[SERP 데이터 구조화]
[x] 5.5.10 parse_serp.js 신규 생성 (organic 7 + PAA 5 + related 8 + KG)
[x] 5.5.11 route_prompt.js SERP 텍스트 연결 방식 변경
[x] 5.5.12 workflow_complete.json Parse SERP Data 노드 추가 + 연결

[검증 확장]
[x] 5.5.13 prompt_d_verification.md 4항목 확장 (is_complete, is_useful)
[x] 5.5.14 quality_score (0-100) 필드 추가
[x] 5.5.15 parse_verification.js 4항목 판정 로직 업데이트
[x] 5.5.16 validate_structure.js 신규 생성 (H2/테이블/코드블록/FAQ)

[마크다운 품질]
[x] 5.5.17 PostContent.faq_ld_json() 메서드 추가
[x] 5.5.18 tistory_editor.py FAQ LD+JSON 스키마 자동 주입

[검증 대기]
[ ] 5.5.19 프롬프트 A 키워드 수동 트리거 → 1500자+ 확인
[ ] 5.5.20 프롬프트 B 키워드 수동 트리거 → 2000자+ 확인
[ ] 5.5.21 프롬프트 C 키워드 수동 트리거 → 2000자+ 확인
[ ] 5.5.22 validate_structure.js H2/테이블/코드블록 카운트 정상
[ ] 5.5.23 4항목 검증 모두 true + quality_score 70점+ 확인
[ ] 5.5.24 E2E 발행 후 FAQ LD+JSON 정상 렌더링 확인
```

### Phase 5~7 체크리스트

```
[Phase 5: 운영 안정화]
[x] 5.1 2일 연속 자동 실행 성공 — cron 09:00 AM 매일 자동 발행 확인 (2026-03-09)
[x] 5.2 로그 점검 체계 구축 — logs/ 디렉토리 + 30일 자동 정리
[x] 5.3 Google Search Console 등록 + sitemap 제출
[x] 5.4 Google Analytics 4 설치 — G-4Y6XE181NC (2026-03-09)
[x] 5.5 네이버 서치어드바이저 등록 (2026-03-09)
[x] 5.6 첫 5건 수동 색인 요청 — GSC URL Inspection API 자동화 완료
[x] 5.7 성과 대시보드 W1 데이터 기록 — DASHBOARD.md 생성 (2026-03-09)
[x] 5.8 발행 품질 검수 — FAQ 스키마, 내부 링크, 카테고리 자동 분류 검증 완료
[x] 5.9 레거시 코드 완전 폐기 — legacy/ 디렉토리 이미 삭제됨

[Phase 6: 콘텐츠 누적 + SEO]
[x] 6.1 주 3~5건 안정 발행 확인 — 매일 5건 자동 발행 (MAX_POSTS=5)
[ ] 6.2 프롬프트 튜닝 (통과율 85%+)
[x] 6.3 내부 링크 구조 강화 (허브-스포크) — InternalLinkService 도입 완료
[ ] 6.4 FAQ 리치 스니펫 색인 확인
[x] 6.5 총 20건 발행 달성 — 현재 256건 발행 (tistory.com/256)
[ ] 6.6 제목/메타 A/B 테스트
[ ] 6.7 반응형 스킨 + Core Web Vitals
[x] 6.8 카테고리 정비 — site_profile.json + 자동 분류 + Tistory 동기화 완료

[Phase 7: 성장 + 수익화]
[ ] 7.1 W7~8 게이트: 노출 500+ / 색인 10+
[x] 7.2 애드센스 승인 완료 (2026-03-09)
[ ] 7.3 광고 배치 최적화
[ ] 7.4 고CPC 키워드 집중
[ ] 7.5 W11~12 게이트: 일 유입 20명
[ ] 7.6 CPA 제휴 검토
[ ] 7.7 워드프레스 전환 검토 (피벗 시)

[Phase 8: 동적 카테고리 관리 (2026-03-09)]
[x] 8.1 site_profile.json 외부 설정 파일 (CATEGORY_MAP 하드코딩 제거)
[x] 8.2 SiteProfile/CategoryMapping frozen VO + Port & Adapter
[x] 8.3 키워드→카테고리 자동 분류 (Step 1.5)
[x] 8.4 --sync-categories CLI (Tistory 카테고리 동기화)
[x] 8.5 하위 카테고리 재귀 파싱 (children 지원)
[x] 8.6 단위 테스트 355건 통과 + 통합 테스트 6건
[x] 8.7 PAGESPEED_API_KEY 등록 (CWV 25,000건/일)
```
