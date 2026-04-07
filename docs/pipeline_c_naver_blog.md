# Pipeline C: 네이버 블로그 자동 발행

> **STATUS: NO-GO (2026-04-06 아카이브)**
>
> writePost API가 2020-05-06에 공식 폐지됨. "API 우선 + Selenium 폴백" 아키텍처 성립 불가.
> Selenium 단독 운영의 ROI가 성립하지 않으며, 계정 제재 리스크가 보상을 초과.
> 재검토 조건: Section 14.1 CONDITIONAL-GO 요건 3가지 참조.
>
> **대안**: 네이버 카페 API (글쓰기 200회/일 공식 지원) → 별도 Pipeline D로 검토 예정.

---

## 1. 개요

기존 시스템은 Tistory 발행(Pipeline B)에 특화되어 있다. 네이버 블로그를 추가하여 트래픽 채널을 이원화하고, 네이버 검색 노출을 확보한다.

| 항목 | Pipeline B (Tistory) | Pipeline C (네이버) |
|------|---------------------|-------------------|
| 타겟 검색엔진 | Google | 네이버 |
| 광고 수익 | AdSense (CPC 300~400원) | 애드포스트 (CPC 10~20원) |
| 일일 발행 한도 | 15건 | ~100건 (자동화 감지 시 24h 제재) |
| 발행 방식 | Selenium (TinyMCE 주입) | Open API + Selenium Fallback |
| 실행 시각 | 09:00 AM | 10:00 AM (Pipeline B 이후) |

### 1.1 목적

- 네이버 검색 유입 확보 (한국 검색 시장 점유율 약 55%)
- 동일 콘텐츠의 플랫폼별 최적화 발행 (Google SEO vs 네이버 SEO)
- Pipeline A가 생성한 콘텐츠를 Tistory + 네이버 동시 활용

### 1.2 콘텐츠 소스

Pipeline A(n8n)가 생성한 콘텐츠를 공유한다. 단, 네이버 최적화를 위해 변환 레이어를 추가한다.

```
Google Sheets (발행완료 상태)
    ↓ 동일 콘텐츠 읽기
Pipeline C (네이버 변환 + 발행)
    ↓ 네이버 발행 완료 시
Google Sheets (네이버발행완료 컬럼 업데이트)
```

---

## 2. 아키텍처

### 2.1 계층 구조

기존 DDD 4-Layer를 유지하되, Infrastructure에 네이버 어댑터를 추가한다.

```
Interface (cli.py --naver)
    ↓
Application (PublishNaverUseCase)
    ↓
Domain (Post, NaverBlogPort)
    ↑
Infrastructure (NaverBlogAPIAdapter / NaverBlogSeleniumAdapter)
```

### 2.2 발행 전략: API 우선 + Selenium 폴백

```
발행 요청
    ↓
[1차] Naver Open API (writePost.json)
    ├─ 성공 → 완료
    └─ 실패 (토큰 만료, 서버 에러)
        ↓
    [토큰 갱신 시도]
        ├─ 성공 → API 재시도
        └─ 실패
            ↓
        [2차] Selenium Fallback (SmartEditor 자동화)
            ├─ 성공 → 완료
            └─ 실패 → FAILED 상태로 기록
```

API 우선 이유:
- 속도: API 1~2초 vs Selenium 30~60초
- 안정성: DOM 변경에 영향 없음
- 봇 탐지 위험 낮음

### 2.3 시트 컬럼 확장

기존 시트에 네이버 전용 컬럼 4개를 추가한다.

| 컬럼명 | 용도 |
|--------|------|
| 네이버상태 | 대기/발행중/발행완료/발행실패/스킵 |
| 네이버URL | 발행된 네이버 블로그 글 URL |
| 네이버발행일시 | 발행 시각 (ISO 8601) |
| 네이버에러 | 실패 시 에러 메시지 |

---

## 3. 네이버 Open API 연동

### 3.1 사전 준비

1. [네이버 개발자 센터](https://developers.naver.com) 애플리케이션 등록
2. 사용 API: "블로그" 선택
3. 서비스 URL + Callback URL 설정 (로컬: `http://localhost:8989/callback`)
4. Client ID / Client Secret 발급

### 3.2 인증 흐름 (OAuth 2.0)

```
[1] 최초 인증 (수동, 1회)
    브라우저로 인증 URL 열기
    → 네이버 로그인 + 권한 동의
    → Callback으로 code 수신
    → code → access_token + refresh_token 교환
    → 토큰을 .env 또는 token.json에 저장

[2] 이후 자동 갱신
    access_token 만료 시 (보통 1시간)
    → refresh_token으로 자동 갱신
    → refresh_token 만료 시 (보통 1년) 재인증 필요
```

### 3.3 API 스펙

**블로그 글쓰기**

```
POST https://openapi.naver.com/blog/writePost.json

Headers:
  Authorization: Bearer {access_token}

Form Data:
  title: 글 제목
  contents: 본문 (HTML)
  categoryNo: 카테고리 번호 (0 = 미분류)
  tags: 태그 (쉼표 구분)
```

**카테고리 조회**

```
GET https://openapi.naver.com/blog/listCategory.json

Headers:
  Authorization: Bearer {access_token}

Response:
  { "message": { "result": { "categories": [...] } } }
```

### 3.4 환경변수

```env
# .env 추가
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
NAVER_ACCESS_TOKEN=
NAVER_REFRESH_TOKEN=
NAVER_BLOG_ID=           # 블로그 아이디 (URL의 blog.naver.com/{id})
NAVER_DAILY_LIMIT=10     # 일일 발행 한도 (보수적 설정)
```

---

## 4. 콘텐츠 변환

Tistory용 콘텐츠를 네이버에 맞게 변환한다. 핵심 차이점을 반영하는 변환 레이어가 필요하다.

### 4.1 변환 항목

| 항목 | Tistory | 네이버 | 변환 로직 |
|------|---------|--------|----------|
| Mermaid 다이어그램 | `<div class="mermaid-diagram"><svg>...</svg></div>` | `<img src="kroki_url">` (PNG 변환) | SVG → PNG URL로 교체 |
| 코드블록 | `<pre><code class="language-bash">` + inline CSS | `<pre><code>` (네이버 기본 스타일) | inline CSS 제거 |
| 내부 링크 | `kimsanghyeon.tistory.com/123` | 네이버 블로그 내부 링크 또는 제거 | URL 매핑 또는 제거 |
| FAQ Schema | `<script type="application/ld+json">` | 제거 (네이버 미지원) | JSON-LD 스크립트 제거 |
| 이미지 | 외부 URL (Unsplash/Pexels) | 동일 URL 유지 또는 네이버 이미지 업로드 | 검증 후 유지 |
| 메타 태그 | og:title, og:description | API 파라미터로 전달 | HTML에서 제거 |
| 광고 영역 | AdSense 스크립트 | 애드포스트 (자동 삽입) | 광고 스크립트 제거 |

### 4.2 네이버 SEO 최적화 (추가 처리)

Tistory 콘텐츠는 Google SEO에 최적화되어 있다. 네이버 검색 노출을 위해 다음을 추가한다.

| 항목 | 설명 |
|------|------|
| 제목 | 동일 유지 (50~60자, 키워드 포함) |
| 본문 길이 | 3,000자 이상 유지 (네이버도 장문 선호) |
| 이미지 수 | 최소 3개 권장 (네이버 품질 점수에 영향) |
| 태그 | 네이버 인기 태그 반영 (최대 10개) |
| 소제목 구조 | H2/H3 유지 (네이버도 구조화된 글 선호) |

### 4.3 콘텐츠 중복 처리

동일 콘텐츠를 두 플랫폼에 발행하면 Google이 중복 콘텐츠로 판단할 수 있다.

**완화 전략:**
- 네이버 발행 시 본문 도입부 2~3문장을 네이버용으로 리라이팅
- canonical URL 미설정 (Tistory가 원본, 네이버는 파생)
- 발행 시간차 (Tistory 09:00 → 네이버 10:00, 최소 1시간 간격)
- 네이버에서는 비공개 발행 후 24시간 뒤 공개 전환 (선택적)

---

## 5. 파일 구조

```
src/
├── domain/
│   └── ports/
│       └── naver_blog_port.py          # NaverBlogPort ABC (BrowserPort와 동일 인터페이스)
│
├── application/
│   └── use_cases/
│       └── publish_naver.py            # PublishNaverUseCase
│
├── infrastructure/
│   └── naver/
│       ├── __init__.py
│       ├── oauth_client.py             # OAuth 2.0 토큰 관리 (발급/갱신/저장)
│       ├── api_adapter.py              # Open API 기반 발행 (NaverBlogPort 구현)
│       ├── selenium_adapter.py         # Selenium 폴백 (NaverBlogPort 구현)
│       ├── naver_auth.py               # Selenium 로그인 자동화
│       ├── content_converter.py        # Tistory HTML → 네이버 HTML 변환
│       └── category_mapper.py          # 카테고리 ID 매핑
│
└── interface/
    └── cli.py                          # --naver 플래그 추가
```

### 5.1 Port 인터페이스

```python
# src/domain/ports/naver_blog_port.py
from abc import ABC, abstractmethod
from src.domain.entities.post import Post
from src.domain.value_objects.publish_result import PublishResult

class NaverBlogPort(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def login(self) -> bool: ...

    @abstractmethod
    def publish(self, post: Post) -> PublishResult: ...

    @abstractmethod
    def list_categories(self) -> list[dict]: ...
```

### 5.2 Use Case

```python
# src/application/use_cases/publish_naver.py
class PublishNaverUseCase:
    def __init__(
        self,
        post_repo: PostRepository,
        naver_port: NaverBlogPort,
        converter: ContentConverter,
        quota: QuotaManager,
    ):
        ...

    def execute(self, limit: int = 5) -> PublishReport:
        # 1. Tistory 발행완료 + 네이버 미발행 포스트 조회
        # 2. 콘텐츠 변환 (Tistory HTML → 네이버 HTML)
        # 3. API 발행 시도 → 실패 시 Selenium 폴백
        # 4. 시트 업데이트 (네이버상태/네이버URL/네이버발행일시)
        ...
```

---

## 6. 상태 관리

### 6.1 발행 대상 필터링

```
조건: 상태 = '발행완료' AND 네이버상태 IN ('대기', '발행실패', NULL)
```

Tistory에 먼저 발행된 글만 네이버에 발행한다. Pipeline A → Pipeline B → Pipeline C 순서를 보장.

### 6.2 상태 전이

```
(없음/대기)
    ↓ 발행 시작
  발행중
    ├─ 성공 → 발행완료 (URL + 일시 기록)
    └─ 실패 → 발행실패 (에러 메시지 기록)
                  ↓ 다음 실행 시 재시도
                발행중
```

### 6.3 스킵 조건

- 코드블록 5개 이상인 글 → 네이버 에디터 렌더링 불안정, 스킵 고려
- 본문 10,000자 초과 → 네이버 API 제한 가능성, 분할 발행 또는 스킵
- Mermaid 다이어그램 3개 이상 → PNG 변환 시간 과다, 축소 고려

---

## 7. 봇 탐지 회피

네이버는 Tistory보다 강한 자동화 감지 로직을 가지고 있다.

### 7.1 API 발행 시

| 항목 | 설정 |
|------|------|
| 발행 간격 | 300~600초 (5~10분) 랜덤 딜레이 |
| 일일 한도 | 10건/일 (보수적, 추후 단계적 확대) |
| 발행 시간대 | 10:00~18:00 (업무 시간 내) |
| 주말 발행 | 비활성 (자연스러운 패턴) |

### 7.2 Selenium 폴백 시

| 항목 | 설정 |
|------|------|
| User-Agent | 실제 Chrome UA (SeleniumBase undetected mode) |
| 마우스 이동 | 자연스러운 커서 패턴 |
| 타이핑 속도 | 50~150ms/자 랜덤 |
| user_data_dir | 쿠키 영속화 (매번 로그인 회피) |

### 7.3 계정 제재 대응

```
[감지 시] "ID당 글 발행 기준 초과" 응답
    ↓
[자동 처리]
1. DailyPublishLimitError 발생
2. 배치 즉시 중단
3. 시트에 "일일한도초과" 에러 기록
4. 24시간 후 자동 재시도 (다음날 cron)
```

---

## 8. CLI 인터페이스

```bash
# 네이버 발행 (기본 5건)
python -m src.interface.cli --naver

# 네이버 발행 (건수 지정)
python -m src.interface.cli --naver --limit 3

# 네이버 토큰 초기 설정
python -m src.interface.cli --naver-auth

# 네이버 카테고리 동기화
python -m src.interface.cli --naver-sync-categories

# Tistory + 네이버 동시 발행
python -m src.interface.cli --all-platforms
```

---

## 9. 구현 단계

### Phase 1: 기반 구축

- [ ] 네이버 개발자 센터 앱 등록 + OAuth 설정
- [ ] `NaverBlogPort` ABC 정의
- [ ] `OAuthClient` 구현 (토큰 발급/갱신/저장)
- [ ] `--naver-auth` CLI 명령 (최초 토큰 획득)
- [ ] Google Sheets 컬럼 4개 추가

### Phase 2: API 발행

- [ ] `NaverBlogAPIAdapter` 구현 (writePost.json)
- [ ] `ContentConverter` 구현 (Tistory HTML → 네이버 HTML)
- [ ] `CategoryMapper` 구현 (listCategory.json → 매핑)
- [ ] `PublishNaverUseCase` 구현
- [ ] 테스트 블로그에서 API 발행 검증

### Phase 3: Selenium 폴백

- [ ] `NaverAuth` 구현 (네이버 로그인 자동화)
- [ ] `NaverBlogSeleniumAdapter` 구현 (SmartEditor 자동화)
- [ ] API 실패 시 자동 폴백 로직
- [ ] 발행 후 URL 검증 (HTTP 200 확인)

### Phase 4: 통합 및 안정화

- [ ] `--naver` CLI 플래그 통합
- [ ] 일일 쿼터 관리 (QuotaManager 확장)
- [ ] 에러 처리 + 재시도 로직
- [ ] 중복 콘텐츠 변환 (도입부 리라이팅)
- [ ] cron 설정 (10:00 AM)

### Phase 5: 모니터링

- [ ] 네이버 발행 상태 대시보드 (`--status` 확장)
- [ ] 네이버 검색 색인 상태 점검 (선택)
- [ ] Slack/Telegram 알림 확장

---

## 10. 리스크 및 완화

| 리스크 | 심각도 | 완화 방안 |
|--------|--------|----------|
| 자동화 감지 → 계정 제재 | HIGH | 일일 10건 보수적 한도, 자연스러운 딜레이, 주말 비활성 |
| 네이버 API 문서 부족 | MEDIUM | 테스트 블로그에서 API 응답 역엔지니어링, 개발자 포럼 활용 |
| SmartEditor DOM 변경 | MEDIUM | API 우선 전략으로 Selenium 의존도 최소화 |
| 중복 콘텐츠 페널티 | MEDIUM | 도입부 리라이팅, 시간차 발행, canonical 미설정 |
| OAuth 토큰 만료 | LOW | refresh_token 자동 갱신, 만료 시 Slack 알림 |
| 네이버 블로그 API 중단 | LOW | Selenium 폴백으로 자동 전환 |

---

## 11. 성공 기준

| 지표 | 목표 |
|------|------|
| 발행 성공률 | 95% 이상 |
| 일일 발행 건수 | 5~10건 (안정화 후) |
| 네이버 검색 노출 | 발행 후 48시간 내 색인 |
| 에러 자동 복구율 | 80% 이상 (API 실패 → Selenium 폴백) |
| 계정 제재 발생 | 0건/월 |

---

## 12. 리뷰 피드백 및 미결 사항

### 12.1 CEO/전략 관점 (2026-04-04 리뷰)

#### ROI 경고

- 네이버 애드포스트 CPC(10~20원)는 Tistory AdSense CPC(300~400원)의 1/20~1/30 수준
- 순수 광고 수익 기준 Pipeline C의 ROI가 성립하지 않을 가능성 높음
- **착수 전 결정 필요**: 네이버 채널의 목적이 (1) 애드포스트 수익 (2) Tistory로의 트래픽 허브 (3) B2B 리드 채널 중 어떤 것인지 명확히 해야 함
- 목적이 애드포스트 수익이라면 Pipeline B 최적화가 우선

#### 우선순위 재검토

Pipeline C 개발보다 선행되어야 할 기존 과제들:

| 과제 | 상태 | 영향도 |
|------|------|--------|
| 발행 후 URL 캡처 버그 (/manage/posts/) | 미해결 | 색인 제출, sitemap, 내부 링크에 영향 |
| CWV 최적화 (LCP 14~17s, CLS 0.3) | 미최적화 | Google 검색 순위 하락 |
| 콘텐츠 품질 향상 (quality_score 기준 강화) | 개선 여지 있음 | 기존 트래픽 2~3배 증가 가능 |
| 빈 본문 기존 포스트 삭제/재발행 (#163~#170) | 미처리 | SEO 부정적 |

#### 대안 검토

| 채널 | 장점 | 단점 |
|------|------|------|
| 네이버 블로그 | 네이버 검색 노출 | CPC 낮음, 자동화 감지 강함 |
| 브런치 | 네이버 노출 + 높은 CPC | API 안정적 |
| LinkedIn Articles | B2B 타겟 오디언스 직접 도달 | 한국어 콘텐츠 소비 한정적 |
| 미디움 | Google SEO 기여 + 백링크 | 한국어 시장 작음 |

#### 권고: MVP 접근

착수 시 전체 Phase 1~5를 한 번에 진행하지 말고 MVP로 검증:

1. **Day 1**: 네이버 개발자센터 앱 등록 + writePost API 1건 호출 테스트
2. API 불가 시 → 전체 계획 재검토 또는 폐기
3. API 가능 시 → 주 3~5건 수동 운영 (2주)
4. 2주 후 네이버 검색 노출 실측치 확인
5. 실측 ROI 기반으로 자동화 투자 범위 결정

---

### 12.2 시니어 엔지니어 관점 (2026-04-04 리뷰)

#### CRITICAL: API 실현 가능성 미검증

- 네이버 블로그 글쓰기 API(`writePost.json`)는 신규 앱 등록 시 글쓰기 권한이 별도 심사 대상
- 개인 개발자에게 잘 발급되지 않을 가능성 있음
- API 불가 시 "API 우선 + Selenium 폴백" 아키텍처 전체가 무너짐 → Selenium만으로 재설계 필요
- **Phase 0(API 검증)을 반드시 최우선으로 실행해야 함**

#### CRITICAL: Post 엔티티 확장 전략 미결

현재 `Post` 엔티티는 단일 플랫폼(Tistory)을 전제로 설계됨:
- `status`, `published_url`, `entry_id`가 모두 Tistory 전용
- 네이버 필드를 Post에 추가하면 플랫폼별 필드 증식 (WordPress, Medium 추가 시 악화)
- `mark_publishing()`은 PENDING에서만 가능 → 이미 PUBLISHED인 Post를 네이버로 발행 시 상태 머신 충돌

**해결 방안 (택 1):**

| 방안 | 장점 | 단점 |
|------|------|------|
| A. Post에 네이버 필드 추가 | 구현 빠름 | 엔티티 오염, 플랫폼 추가 시 증식 |
| B. PlatformPublishRecord VO 도입 | 확장성, DDD 정합 | 기존 상태 머신 전면 리팩터링 |
| C. 시트 레벨에서만 관리 (Post 불변) | 기존 코드 변경 없음 | DDD 순수성 훼손, 로직이 인프라로 유출 |

→ **방안 C를 1차로 채택하되, 기술 부채로 기록하고 향후 멀티 플랫폼 확장 시 방안 B로 전환 권고**

#### HIGH: Port 설계 개선

- `NaverBlogPort`와 `BrowserPort`가 거의 동일한 인터페이스 → 중복 Port
- `list_categories()`를 발행 Port에 넣으면 ISP 위반 (기존 `CategorySyncPort` 참고)
- API Adapter에서 `start()/stop()`이 no-op → 인터페이스가 Selenium에 맞춰 설계된 신호
- **폴백 로직은 Composite Adapter 패턴으로 Infrastructure에 배치** (UseCase가 어댑터 선택을 알 필요 없음)

```python
# 권장: infrastructure/naver/composite_adapter.py
class NaverBlogCompositeAdapter(NaverBlogPort):
    def __init__(self, api: NaverBlogAPIAdapter, selenium: NaverBlogSeleniumAdapter):
        self._api = api
        self._selenium = selenium

    def publish(self, post: Post) -> PublishResult:
        result = self._api.publish(post)
        if result.success:
            return result
        return self._selenium.publish(post)
```

#### HIGH: 콘텐츠 변환 복잡도

- `content_converter.py` 단일 파일에 7개 변환 로직 → **Pipeline 패턴으로 분리**
- Mermaid SVG → PNG: Kroki는 소스→렌더링 서비스이지 SVG→PNG 변환 아님. 별도 변환 필요 (cairosvg 등)
- 도입부 리라이팅은 LLM API 호출 필요 → Phase 4가 아닌 별도 기획으로 분리

#### MEDIUM: 기타

- 토큰 저장: `.env` 파일을 프로그램이 수정하는 것은 부적절 → `token.json`에 별도 저장 (.gitignore)
- `--all-platforms` 플래그: Pipeline 간 격리 원칙에 반함 → 제거하고 별도 cron 유지
- QuotaManager: 플랫폼별 쿼터 분리 필요 (`NaverQuotaManager` 별도 또는 플랫폼 파라미터 추가)
- 네이버 2단계 인증: Selenium 사용 시 CAPTCHA/OTP 처리 방안 미명시
- 테스트 전략 섹션 전체 누락 → 추가 필요

#### 예상 기술 부채

| 항목 | 심각도 |
|------|--------|
| Post 엔티티에 플랫폼별 필드 증식 (방안 A 채택 시) | HIGH |
| BrowserPort / NaverBlogPort 중복 인터페이스 | MEDIUM |
| ContentConverter 단일 파일 7개 변환 로직 | MEDIUM |
| GoogleSheetsPostRepository 비대화 | MEDIUM |
| 플랫폼별 상태 머신 미분리 | HIGH |

---

### 12.3 착수 전 체크리스트

- [ ] 비즈니스 목적 확정 (수익 / 트래픽 허브 / 리드)
- [ ] Pipeline B 미해결 과제 우선순위 검토
- [x] ~~Phase 0: 네이버 개발자센터 앱 등록 + writePost API 실제 호출 검증~~ → **API 폐지 확인됨 (13절 참조)**
- [ ] Post 엔티티 확장 전략 확정 (방안 A/B/C)
- [ ] ~~폴백 로직 아키텍처 위치 확정 (Composite Adapter)~~ → Selenium 단독으로 변경
- [ ] 테스트 전략 수립

---

## 13. Phase 0 검증 결과 (2026-04-05, gstack browse 실행)

### 13.1 검증 방법

gstack headless browser로 네이버 개발자센터를 직접 탐색하고, Firecrawl 검색으로 관련 자료를 수집.

### 13.2 결론: **writePost API는 2020년 5월 6일에 공식 폐지됨**

네이버 블로그 글쓰기 API(`writePost.json`)는 더 이상 존재하지 않는다. 기획의 "API 우선 + Selenium 폴백" 아키텍처는 성립 불가.

### 13.3 검증 근거

| # | 검증 항목 | 결과 | URL |
|---|----------|------|-----|
| 1 | 블로그 API 제품 페이지 | **404** | `developers.naver.com/products/blog/` |
| 2 | 블로그 글쓰기 API 문서 | **404** | `developers.naver.com/docs/blog/post/` |
| 3 | writePost.json 문서 | **404** | `developers.naver.com/docs/blog/post/writePost/writePost.md` |
| 4 | 네이버 오픈API 전체 목록 | 블로그 글쓰기 API **미포함** | `developers.naver.com/docs/common/openapiguide/apilist.md` |
| 5 | Products 사이드바 | 블로그 카테고리 **없음** | `developers.naver.com/products/intro/plan/plan.md` |
| 6 | Documents 사이드바 | 블로그 문서 섹션 **없음** | `developers.naver.com/docs/common/openapiguide/` |
| 7 | 개발자 포럼 질문 (2025.11) | 사용자가 writePost API 못 찾겠다고 문의, **답변 없음** | `developers.naver.com/forum/posts/37487` |
| 8 | 블로그 포스트 (2020.04.07) | "네이버 블로그 글쓰기 API 5월 6일 이후 기능 종료" 공식 안내 | `blog.naver.com/dksoft99/221894934546` |

### 13.4 현재 네이버 오픈API 전체 목록 (2026-04-05 기준)

**로그인 방식 (OAuth 2.0):**
- 네이버 로그인 (프로필 조회)
- **카페** (가입 50회/일, 글쓰기 200회/일) ← 블로그가 아닌 카페만 가능
- 캘린더 (일정 추가 5,000회/일)

**비로그인 방식 (Client ID/Secret):**
- 데이터랩 (검색어/쇼핑 트렌드, 1,000회/일)
- 검색 (뉴스/블로그/쇼핑 등 검색, 25,000회/일) ← 검색만, 글쓰기 불가
- 이미지/음성 캡차
- 네이버 공유하기, 네이버 오픈메인
- Clova Face Recognition

### 13.5 아키텍처 변경 영향

| 기존 계획 | 변경 후 |
|-----------|---------|
| API 우선 + Selenium 폴백 | **Selenium 단독** |
| `NaverBlogAPIAdapter` + `NaverBlogSeleniumAdapter` | `NaverBlogSeleniumAdapter`만 |
| `OAuthClient` (토큰 관리) | **불필요** (삭제) |
| `CompositeAdapter` (API/Selenium 전환) | **불필요** (삭제) |
| 발행 속도 1~2초/건 (API) | 30~60초/건 (Selenium) |
| 봇 탐지 위험 낮음 (API) | **봇 탐지 위험 높음** (Selenium) |
| `--naver-auth` CLI | Selenium 쿠키 관리로 대체 |

### 13.6 Selenium 자동 발행 가능성

웹 검색 결과, Selenium + pyperclip + pyautogui로 네이버 블로그 자동 발행에 성공한 사례가 다수 확인됨.

**주요 기술 과제:**

| 과제 | 설명 | 해결 사례 |
|------|------|----------|
| 네이버 로그인 봇 탐지 | pyperclip으로 복붙 (send_keys 차단) | gpters.org 구현 |
| SmartEditor iframe | `mainFrame` iframe으로 focus 전환 필요 | `driver.switch_to.frame('mainFrame')` |
| 새 창으로 열리는 에디터 | `driver.switch_to.window(driver.window_handles[-1])` | gpters.org 구현 |
| 에디터 내 팝업 (작성 중 글, 도움말) | try/except로 팝업 감지 후 닫기 | gpters.org 구현 |
| 본문 입력 | send_keys() 미동작 → pyautogui.hotkey('ctrl', 'v') | gpters.org 구현 |
| CAPTCHA / 2단계 인증 | user_data_dir로 세션 유지하여 회피 | Pipeline B 패턴 |

### 13.7 수정된 파일 구조

```
src/infrastructure/naver/
├── __init__.py
├── selenium_adapter.py      # NaverBlogPort 구현 (Selenium 단독)
├── naver_auth.py            # 네이버 로그인 (pyperclip)
├── content_converter.py     # Tistory HTML → 네이버 HTML
├── category_mapper.py       # 카테고리 매핑
└── smart_editor.py          # SmartEditor 조작 로직 (iframe, 팝업, 입력)
```

삭제 대상:
- ~~`oauth_client.py`~~ (API 없으므로 OAuth 불필요)
- ~~`api_adapter.py`~~ (API 폐지)
- ~~`composite_adapter.py`~~ (폴백 불필요)

### 13.8 리스크 재평가

| 리스크 | 기존 심각도 | 변경 심각도 | 사유 |
|--------|-----------|-----------|------|
| 네이버 블로그 API 중단 | LOW | **CONFIRMED** | 2020년 이미 폐지됨 |
| 자동화 감지 → 계정 제재 | HIGH | **CRITICAL** | API 폴백 없이 Selenium 단독이므로 위험도 상승 |
| SmartEditor DOM 변경 | MEDIUM | **HIGH** | Selenium 단독 의존으로 DOM 변경이 전체 장애로 직결 |
| 네이버 API 문서 부족 | MEDIUM | **N/A** | API 자체가 없으므로 해당 없음 |

### 13.9 권고사항

1. **"API 우선" 아키텍처 전면 폐기** → Selenium 단독으로 재설계
2. 기획서 Section 2.2, 3.x, 5.x에서 API 관련 내용 제거 필요
3. Pipeline B(Tistory)의 SeleniumBase 패턴을 최대한 재활용
4. 봇 탐지 회피 전략을 더 강화 (일일 5건 이하, user_data_dir 세션 영속화)
5. 네이버 카페 API (글쓰기 200회/일)가 대안 채널로 고려 가능 → 별도 검토

---

## 14. 2차 리뷰 (2026-04-05, Phase 0 검증 반영)

### 14.1 CEO/전략 리뷰

#### VERDICT: NO-GO (현 상태 기준)

CONDITIONAL-GO 전환 요건 3가지 모두 충족 시 재검토 가능.

#### Go/No-Go 판단

API가 2020년에 폐지된 시점에서, 이 기획서의 핵심 전제가 무너졌다. "API 우선 + Selenium 폴백"이 아닌 "Selenium 단독"은 기획 당시와 완전히 다른 리스크 프로파일의 프로젝트다. 기존 기획서 기반 Go 결정은 내릴 수 없으며, Selenium 단독 아키텍처로 재기획 후 재검토 필요.

#### ROI 재계산: 성립하지 않음

| 축 | 평가 |
|----|------|
| **수익** | 애드포스트 CPC 10~20원, 일 5~10건 = 월 수천 원. 개발비 회수 불가 |
| **비용** | Selenium 30~60초/건, 브라우저 인스턴스 상시 실행, SmartEditor DOM 변경 시 긴급 유지보수 |
| **리스크** | 계정 제재 시 블로그 전체 비공개/영구정지. B2B 채널로 활용 중이면 치명적 손실 |

→ 리스크 대비 기대 수익이 비대칭적으로 불리.

#### 기회비용: Pipeline B 최적화가 우선

| 대안 | 예상 ROI | 근거 |
|------|---------|------|
| **CWV 최적화 (LCP 14~17s → <4s)** | 기존 트래픽 30~50% 유입 증가 | LCP 14초 = "Poor". 해결 시 Google 순위 즉시 상승 |
| **URL 캡처 버그 수정** | 색인/sitemap/내부 링크 정상화 | Pipeline B의 근본 품질 훼손 버그 |
| **콘텐츠 품질 향상** | 기존 트래픽 2~3배 | quality_score 기준 강화 + 빈 본문 정리 |

→ 같은 2~3주를 CWV + URL 버그에 쓰면 AdSense CPC 300~400원 기반 확실한 수익 증대 가능.

#### 문서 정합성: 심각한 모순

Section 1 표, 2.2 전체 흐름도, 3 전체(65행), 5 파일 구조, 9 Phase 1~2, 10 리스크 표가 모두 Section 13과 모순. 현 상태로는 기획서가 아닌 히스토리 로그. 실행 지침으로 사용 불가.

#### 계정 제재 리스크: 수용 불가

네이버는 SmartEditor 내부에서 마우스 이벤트 패턴, 타이핑 속도, 브라우저 핑거프린트를 종합 분석. `pyautogui.hotkey('ctrl', 'v')` 방식은 인간 패턴과 완전히 다름. 건수 제한으로 "탐지 확률"을 낮추더라도, "탐지 시 손실 규모"로 판단하면 수용 불가.

#### 대안: 네이버 카페 API

| 비교 | 블로그 (Selenium) | 카페 (API) |
|------|-------------------|-----------|
| 방식 | 비공식 Selenium | 공식 API |
| 일일 한도 | ~10건 (자체 제한) | 200회/일 (공식) |
| 봇 탐지 | CRITICAL | LOW |
| 유지보수 | DOM 변경마다 수정 | API 스펙 변경 시만 |

→ **별도 기획서(Pipeline D)로 분리하여 ROI 독립 평가 권고.**

#### CONDITIONAL-GO 전환 요건

1. Pipeline B 안정화 완료 (URL 버그, CWV LCP<4s, 빈 본문 정리)
2. 네이버 채널 비즈니스 목적 확정 + ROI 모델 수립 (애드포스트 외 정량적 가치)
3. Selenium 단독 재기획서 작성 (API 내용 제거, BCP 포함, 테스트 전략 포함)

---

### 14.2 시니어 엔지니어 리뷰

#### 이슈 우선순위 요약

| # | 심각도 | 항목 | 해결 방안 |
|---|--------|------|----------|
| 1 | **CRITICAL** | 문서 정합성 | Section 2~6, 9를 Section 13 기준으로 전면 재작성 |
| 2 | **CRITICAL** | 상태 머신 충돌 (PUBLISHED Post 네이버 발행 불가) | 방안 C + `NaverPublishRepository` 별도 Port. Post.status 불변 |
| 3 | **CRITICAL** | 구현 단계 무효 (Phase 1~2가 API 기반) | Selenium 단독 기준 Phase 0~5 재설계 |
| 4 | **CRITICAL** | 봇 탐지 리스크 (API 폴백 없음) | UC 모드 필수, 초기 3건/일, 계정 분리, IP 고려 |
| 5 | **HIGH** | 기존 코드 재활용 구조 미설계 | 공통 유틸리티 추출 (safe_actions.py) |
| 6 | **HIGH** | NaverBlogPort 설계 (BrowserPort 중복) | `list_categories()` 제거, 최소 인터페이스 |
| 7 | **HIGH** | headless에서 pyperclip/pyautogui 불가 | Xvfb + non-headless 또는 JS inject 우선 |
| 8 | **HIGH** | 테스트 전략 전체 누락 | 단위/통합/E2E 3단계 테스트 계획 추가 |
| 9 | **MEDIUM** | ContentConverter 7개 변환 로직 단일 파일 | Pipeline 패턴 분리, 각 변환 함수 독립 테스트 |
| 10 | **MEDIUM** | `--all-platforms` CLI 플래그 | 제거, 별도 cron 유지 |

#### 기존 코드 재활용 분석

**직접 재활용 가능:**
- `human_typing.py` — 그대로 사용
- `dom_selectors.py`의 `find_element()` Fallback Chain 패턴
- `SeleniumBrowserAdapter.start()/stop()` — SB 컨텍스트, user_data_dir 로직
- `_safe_click()` / `_safe_type()` — 3단계 fallback 패턴
- `PublishResult` VO, `DailyPublishLimitError` — 그대로 사용

**패턴 차용 (새로 작성):**
- `kakao_auth.py` → `naver_auth.py` (pyperclip 방식으로 변경)
- `tistory_editor.py` → `smart_editor.py` (완전히 다른 에디터)
- `dom_selectors.py` → `naver_selectors.py` (셀렉터 값 별개)

**공통 유틸리티 추출 권고:**
```
src/infrastructure/browser/
├── common/
│   ├── safe_actions.py      # _safe_click, _safe_type, find_element
│   └── human_typing.py      # (이동)
├── tistory/                 # Tistory 전용
└── naver/                   # 네이버 전용
```

#### 상태 머신 해결: Post 불변 + NaverPublishRepository

```python
class NaverPublishRepository(ABC):
    @abstractmethod
    def find_naver_pending(self, posts: list[Post]) -> list[Post]: ...
    @abstractmethod
    def save_naver_result(self, row_index: int, url: str, status: str) -> None: ...
    @abstractmethod
    def save_naver_error(self, row_index: int, error: str) -> None: ...
```

Post.status는 변경하지 않음. 시트의 네이버 전용 컬럼만 별도 Repository로 관리. 3번째 플랫폼 추가 시 방안 B(PlatformPublishRecord VO)로 전환하는 트리거를 ADR로 기록.

#### headless 환경 기술 리스크

pyperclip + pyautogui는 headless에서 **불가**:
- `pyperclip.copy()`: OS 클립보드 의존, headless에서 xclip/xsel 필요
- `pyautogui.hotkey()`: 화면 좌표 기반, headless에서 완전 불가

**대안:**
1. Xvfb + non-headless (가장 안정적, 서버 설정 추가 필요)
2. JavaScript `document.querySelector().innerHTML = html` 주입
3. Selenium ActionChains

#### 재설계된 구현 단계

| Phase | 내용 | 소요 |
|-------|------|------|
| **0. 선행 리팩토링** | Pipeline B에서 공통 모듈 추출 (safe_actions, human_typing) | 1~2일 |
| **1. Domain + Ports** | NaverBlogPort, NaverPublishRepository, NaverCredentials VO, TDD | 1~2일 |
| **2. 콘텐츠 변환** | ContentConverter Pipeline 패턴, 각 변환 규칙 독립 TDD | 2~3일 |
| **3. Selenium 자동화** | naver_auth, smart_editor, naver_selectors — 핵심 난이도 | 3~5일 |
| **4. UseCase + CLI** | PublishNaverUseCase, --naver, --dry-run | 2~3일 |
| **5. 안정화 + 모니터링** | 에러 처리, 재시도, 알림, cron, 점진 확대 (3→5→10건/일) | 1~2일 |
| **총계** | | **10~15일** |

#### 최종 권고

1. 이 문서를 실행 계획으로 사용하지 말 것. Section 13 기준 전면 재작성 필요.
2. Phase 0 (공통 모듈 추출)은 Pipeline C 착수와 무관하게 즉시 실행 가능. Pipeline B 코드 품질에도 기여.
3. SmartEditor 자동화 PoC를 별도 스파이크로 수행. headless 환경 본문 입력 방식이 핵심.
4. MVP 기준을 "Selenium으로 테스트 계정에 1건 발행 성공"으로 재정의.
