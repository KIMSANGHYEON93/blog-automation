# B2B IT 블로그 자동화 시스템 — 팀 내부 공유 대본

> 예상 발표 시간: 15~20분

---

## 1. 오프닝 (1분)

안녕하세요. 오늘은 저희가 구축한 **B2B IT 블로그 자동화 시스템**을 공유드리겠습니다.

이 시스템은 한마디로, **키워드 리서치부터 콘텐츠 생성, 블로그 발행, SEO 최적화까지 전 과정을 자동화**하는 파이프라인입니다.

현재 **51건 이상의 포스트를 자동 발행**했고, **431개 테스트, 92% 이상의 커버리지**를 유지하고 있습니다.

---

## 2. 왜 만들었나 — 문제 정의 (2분)

B2B IT 블로그를 운영하면서 반복적으로 겪는 문제가 있었습니다.

**첫째, 콘텐츠 생산 병목.**
- 키워드 조사 → 글 작성 → 검수 → 발행까지 포스트 하나에 2~3시간 소요
- 일관된 품질 유지가 어려움

**둘째, 발행 작업의 반복성.**
- Tistory 에디터에 매번 수동으로 HTML 붙여넣기
- 카테고리 설정, 태그 입력, FAQ 스키마 삽입 등 반복 작업
- 하루 최대 15건 제한 관리

**셋째, SEO 사후 관리 부재.**
- 발행 후 구글 색인 여부 미확인
- Core Web Vitals 모니터링 미비
- 내부 링크 전략 부재

이 문제들을 해결하기 위해 **두 개의 자동화 파이프라인**을 설계했습니다.

---

## 3. 시스템 전체 구조 (3분)

### 두 개의 파이프라인

```
┌─────────────────────────────┐     ┌─────────────────────────────┐
│   Pipeline A (n8n)          │     │   Pipeline B (Python/DDD)   │
│   콘텐츠 생성               │     │   블로그 발행               │
│   매일 01:00 AM             │────▶│   매일 09:00 AM             │
│                             │     │                             │
│   n8n + LLM (Gemini/Claude) │     │   Selenium + Google Sheets  │
└─────────────────────────────┘     └─────────────────────────────┘
```

**Pipeline A** — n8n 워크플로우 기반 콘텐츠 생성
- 새벽 1시에 자동 실행
- Google Sheets에서 대기 중인 키워드를 읽어옴
- SerpAPI로 경쟁 페이지 5개 수집
- LLM(Gemini/Claude)이 3가지 프롬프트 템플릿으로 글 생성
  - A: 용어 정의형, B: 비교 분석형, C: 트러블슈팅형
- Claude Haiku가 4가지 항목(정확성, 논리성, 완성도, 유용성)으로 교차 검증
- 통과한 콘텐츠를 Google Sheets에 "발행대기" 상태로 저장

**Pipeline B** — Python DDD 기반 자동 발행 (오늘 발표의 핵심)
- 아침 9시에 자동 실행
- Google Sheets에서 "발행대기" 포스트를 읽어옴
- Selenium으로 Tistory에 자동 로그인 → 에디터 조작 → 발행
- 내부 링크 삽입, HTML 최적화, FAQ 스키마 주입까지 자동 처리
- 발행 결과를 Google Sheets에 업데이트

**두 파이프라인 사이의 버퍼는 Google Sheets**입니다. 이게 Single Source of Truth 역할을 합니다.

---

## 4. 아키텍처 — DDD 4-Layer + Hexagonal (4분)

Pipeline B의 설계 철학을 설명드리겠습니다.

### 왜 DDD를 선택했나

자동화 스크립트를 그냥 절차적으로 짤 수도 있었습니다. 하지만:
- 포스트 상태 관리가 복잡 (9가지 상태 전이)
- 외부 서비스 의존성이 많음 (Tistory, Google Sheets, Google APIs)
- 장기 유지보수와 테스트가 중요

그래서 **DDD 4-Layer + Hexagonal Architecture**를 적용했습니다.

### 레이어 구조

```
Interface (CLI) → Application (Use Cases) → Domain (핵심 로직) ← Infrastructure (어댑터)
```

| 레이어 | 경로 | 역할 | 외부 의존성 |
|--------|------|------|------------|
| **Domain** | `src/domain/` | 핵심 비즈니스 로직 | **없음** (stdlib만) |
| **Application** | `src/application/` | 유스케이스 오케스트레이션 | Domain만 |
| **Infrastructure** | `src/infrastructure/` | 외부 서비스 어댑터 | Domain Port 구현 |
| **Interface** | `src/interface/cli.py` | 진입점 + DI 조립 | 모든 레이어 |

핵심 규칙: **Domain은 외부 패키지를 절대 import하지 않습니다.**
`make validate-ddd` 명령으로 매 빌드마다 이 규칙을 자동 검증합니다.

### Port & Adapter 패턴

Domain에서 인터페이스(Port)를 정의하고, Infrastructure에서 구현(Adapter)합니다.

```
Domain (Port 정의)              Infrastructure (Adapter 구현)
─────────────────               ──────────────────────────────
PostRepository  ◀──────────────  GoogleSheetsPostRepository
BrowserPort     ◀──────────────  SeleniumBrowserAdapter
SeoPort         ◀──────────────  HtmlOptimizer, IndexingChecker
NotificationPort ◀─────────────  SlackAdapter, TelegramAdapter
```

테스트에서는 `InMemoryPostRepository`, `MockBrowserAdapter` 같은 테스트 더블을 주입합니다.
이 덕분에 **외부 서비스 없이도 Domain과 Application 계층의 모든 로직을 테스트**할 수 있습니다.

---

## 5. 핵심 도메인 모델 (3분)

### Post Entity — 상태 머신

이 시스템의 중심에는 `Post` 엔티티가 있습니다. 9가지 상태를 가진 상태 머신입니다.

```
WAITING → GENERATING → PENDING → PUBLISHING → PUBLISHED
                                      ↓
                                    FAILED → (retry) → PENDING

PUBLISHED → REVISION_PENDING → REVISING → PUBLISHED
```

**잘못된 상태 전이를 시도하면 `InvalidStateTransitionError`가 발생합니다.**
예를 들어, WAITING 상태에서 바로 PUBLISHED로 갈 수 없습니다.

주요 검증 로직:
- `is_publishable()`: 상태가 PENDING이고, 콘텐츠가 있고, 품질 점수 70점 이상이어야 발행 가능
- `mark_publishing()`: PENDING → PUBLISHING 전이 + 유효성 검사
- `mark_failed(reason)`: 실패 사유를 기록하며 FAILED로 전이

### Value Objects

13개의 불변 Value Object로 도메인 개념을 표현합니다.

주요 예시:
- **PostContent**: 제목, 본문, 태그, 메타 설명, FAQ를 하나로 묶는 불변 객체
- **PostStatus**: 9가지 상태를 나타내는 Enum
- **PublishResult**: 발행 성공/실패 결과를 담는 객체
- **SiteProfile**: 블로그 카테고리 구성과 키워드 매핑 정보

### Domain Services

복잡한 비즈니스 규칙은 Domain Service로 분리했습니다.

- **InternalLinkService**: Hub-Spoke 내부 링크 전략. 가장 많이 언급되는 포스트를 허브로 식별하고, 4단계 우선순위로 관련 링크를 선정합니다.
- **PublishPolicy**: 일일 발행 한도 관리, 연속 실패 시 중단 정책 (3회 연속 실패 시 배치 중단)
- **RetryPolicy**: 실패 포스트 재시도 로직. 지수 백오프로 재시도 간격을 늘립니다.

---

## 6. 주요 기능 시연 설명 (3분)

### 발행 워크플로우 (PublishPostsUseCase)

```python
execute() 호출 시:
  1. Google Sheets에서 발행대기 포스트 조회 (최대 5건)
  2. 이미 발행된 포스트 목록 로드 (내부 링크용)
  3. 허브 포스트 식별
  4. 브라우저 시작 + 카카오 로그인
  5. 각 포스트마다:
     a. 관련 내부 링크 선정 + 삽입
     b. Markdown → HTML 변환
     c. FAQ JSON-LD 스키마 삽입
     d. HTML 최적화 (lazy loading, LCP 우선순위)
     e. Tistory 에디터에서 발행
     f. 발행 결과 확인 + Google Sheets 업데이트
  6. 최종 통계 반환 (발행 N건, 실패 N건, 스킵 N건)
```

### 고스트 포스트 복구

발행 중에 시스템이 중단되면 포스트가 "발행중(PUBLISHING)" 상태에 멈춥니다.
`ResetStuckPostsUseCase`가 이런 고스트 포스트를 감지하고 자동으로 "발행대기"로 되돌립니다.

### SEO 사후 관리

| 커맨드 | 기능 |
|--------|------|
| `--check-index` | 구글 색인 상태 확인, 미색인 포스트를 수정대기로 전환 |
| `--revise` | 수정대기 포스트를 Tistory에서 업데이트 |
| `--submit-index` | 구글 Indexing API로 URL 제출 |
| `--check-cwv` | PageSpeed Insights로 Core Web Vitals 측정 |
| `--generate-sitemap` | 발행된 포스트로 sitemap.xml 생성 |
| `--discover-keywords` | Google Search Console 데이터로 키워드 발굴 |

---

## 7. 품질 관리 체계 (2분)

### TDD 개발 프로세스

모든 Domain/Application 코드는 TDD로 개발했습니다.

```
RED   → 실패하는 테스트 먼저 작성
GREEN → 테스트 통과하는 최소 코드 구현
REFACTOR → 테스트 유지하며 코드 정리
```

각 사이클을 별도 커밋으로 분리하여 히스토리를 명확하게 관리합니다.

### Quality Gates

| 게이트 | 기준 | 명령어 |
|--------|------|--------|
| 유닛 테스트 | 431개 전체 통과 | `make test-unit` |
| 코드 커버리지 | Domain+App 80% 이상 (현재 92%) | `make coverage` |
| 린트 | ruff 경고 0개 | `make lint` |
| 타입 체크 | mypy 에러 0개 | `make typecheck` |
| DDD 레이어 검증 | 위반 0건 | `make validate-ddd` |

`make quality` 하나로 전체 게이트를 한번에 실행할 수 있습니다.

### 현재 수치

| 지표 | 값 |
|------|---|
| Python 코드 | 6,998줄 |
| 테스트 파일 | 46개 |
| 테스트 케이스 | 431개 |
| 코드 커버리지 | 92%+ |
| 발행 성공 | 51건+ |
| 개발 단계 | Phase 7 (프로덕션 안정화) |

---

## 8. 기술 스택 요약 (1분)

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.9+ |
| 아키텍처 | DDD 4-Layer + Hexagonal |
| 브라우저 자동화 | SeleniumBase |
| 데이터 저장 | Google Sheets (gspread) |
| 콘텐츠 생성 | n8n + Gemini/Claude |
| 교차 검증 | Claude Haiku |
| 키워드 리서치 | SerpAPI + Google Search Console |
| SEO 모니터링 | Google Indexing API + PageSpeed Insights |
| 블로그 플랫폼 | Tistory |
| 알림 | Slack / Telegram |
| 테스트 | pytest + pytest-cov |
| 린트/타입체크 | ruff + mypy |
| 스케줄링 | Cron (01:00 AM / 09:00 AM) |

---

## 9. 배운 점과 향후 계획 (1분)

### 배운 점

1. **DDD가 자동화 프로젝트에서도 효과적**
   - 상태 머신이 복잡한 시스템일수록 Domain 계층 분리의 가치가 큼
   - Port & Adapter로 외부 서비스 교체가 용이 (예: LLM 프로바이더 전환)

2. **TDD가 Selenium 자동화의 안전망**
   - 브라우저 자동화는 본질적으로 불안정 → Domain 로직만이라도 완벽히 테스트
   - 상태 전이 버그를 사전에 차단

3. **Google Sheets가 의외로 좋은 버퍼**
   - 별도 DB 없이 두 파이프라인 연결
   - 수동 개입이 쉬움 (시트에서 직접 상태 수정 가능)

### 향후 계획

- Google Analytics 연동으로 트래픽 기반 콘텐츠 갱신
- A/B 테스트 (제목/메타 설명 변형)
- 소셜 미디어 자동 공유 연동
- 댓글 자동 관리

---

## 10. Q&A

질문 있으시면 편하게 말씀해주세요.

프로젝트 코드는 리포지토리에서 확인하실 수 있고, `masterplan_v2.3.md`에 상세 설계 문서가, `process.md`에 전체 개발 이력이 정리되어 있습니다.

감사합니다.
