# B2B IT 블로그 자동화 마스터 플랜 v2.3

> **문서 버전**: v2.3 (DDD/TDD 아키텍처 적용 + 파이프라인 B 재설계)
> **최종 갱신**: 2026-02-28
> **아키텍처**: 비동기 듀얼 파이프라인 + DDD 4-Layer (Domain-Driven Design)
> **상세 프로세스**: `prosess.md` 참조 (1,207줄, DDD/TDD 개발 프로세스 전문)

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

> v2.2와 동일. 파이프라인 A는 n8n 워크플로우 기반으로 DDD 적용 범위 외.
> 상세 내용은 v2.2 섹션 3 참조.

### 3.1 n8n 워크플로우 노드 명세

| Node | 유형 | 기능 | 입력 | 출력 |
|------|------|------|------|------|
| 1 | Schedule Trigger | 매일 01:00 AM 실행 | - | 트리거 신호 |
| 2 | Google Sheets Read | Status="대기" 행 읽기 | 시트 연결 | 키워드+메타데이터 |
| 3 | HTTP Request (SerpAPI) | Google 검색 스니펫 수집 | 키워드 | 상위 10개 스니펫 |
| 4 | HTTP Request (Claude API) | 콘텐츠 생성 (Sonnet) | 키워드+스니펫+프롬프트 | JSON (제목/본문/메타/FAQ) |
| 5a | Code Node | URL 정규식+DNS 검증 | 생성된 본문 | 검증 결과 |
| 5b | Code Node | 코드 블록 기초 포맷 스크리닝 | 생성된 본문 | 검증 결과 |
| 5c | HTTP Request (Claude API) | 정의 정확성+논리 모순 검증 (Haiku, temp=0) | 생성된 JSON | 통과/실패 판정 |
| 6 | Google Sheets Update | 결과 저장 (Status 변경) | 검증 결과+콘텐츠 | 발행대기/검수필요 |

> 노드별 코드 상세(SerpAPI 파싱, Claude 호출, URL 검증, 코드 lint, 검증 파싱)는 v2.2 섹션 3.2~3.6과 동일하므로 생략.

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
├── prosess.md                           # DDD/TDD 개발 프로세스 (1,207줄)
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

> v2.2와 동일. DDD 리팩토링은 파이프라인 B의 코드 구조만 변경하며, 프롬프트·검증 로직·시트 스키마에는 영향 없음.

**참조**: 마스터 플랜 v2.2 섹션 5 (프롬프트 A/B/C 전문), 섹션 6 (검증 프롬프트 D), 섹션 7 (시트 스키마 A~S열)

핵심 스키마 변경 없음 확인:

| 항목 | v2.2 | v2.3 | 변경 |
|------|------|------|------|
| JSON 필드명 | `content` | `content` | 없음 |
| 시트 컬럼 | A~S열 (19개) | A~S열 (19개) | 없음 |
| 검증 항목 | 2개 (is_accurate, is_logical) | 2개 | 없음 |
| meta_description | 120~155자 | 120~155자 | 없음 |

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

### 14.3 v2.2→v2.3 DDD/TDD 아키텍처 적용 (11건)

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
| `prosess.md` | 마크다운 | v1.0 | DDD/TDD 개발 프로세스 (1,207줄, 코드 전문 포함) |
| `masterplan_v2.2.md` | 마크다운 | v2.2 | 이전 버전 (프롬프트/검증/시트 스키마 전문 참조) |
| `tistory_publisher.py` | Python | v1.0 (레거시) | 모놀리식 파이프라인 B (553줄, Phase 4에서 폐기) |
| `blog-automation/src/` | Python | v2.3 | DDD 4-Layer 파이프라인 B (20+ 파일) |
| `blog-automation/tests/` | Python | v2.3 | 테스트 스위트 (unit+integration+e2e, 50+건) |
| `keyword_calendar_v2.xlsx` | Excel | v2.0 | 키워드 캘린더 템플릿 |

---

> **다음 단계**: Phase 1 실행 또는 Phase 2 TDD 시작 (`prosess.md` 섹션 5.3의 Red-Green-Refactor 사이클 따라 Domain Layer 구현).
