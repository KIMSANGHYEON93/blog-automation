# SEO 성장 전략 — 콘텐츠 품질 혁신 + 데이터 기반 성장 엔진

> **작성일**: 2026-03-11
> **상태**: 승인됨
> **배경**: 100건+ 발행, 1개월+ 운영, 전반적 SEO 성과 저조 (색인/노출/유입 모두 목표 미달)

---

## 문제 정의

현재 시스템은 자동 생성 → 자동 발행까지 안정적으로 동작하지만, SEO 성과가 기대에 미치지 못함:

- **콘텐츠 품질**: 자동 생성 콘텐츠가 Google의 E-E-A-T 기준에 부족할 가능성
- **콘텐츠 깊이**: 평균 1500자 수준의 짧은 글이 검색 순위 경쟁에서 불리
- **키워드 중복**: 유사 키워드로 비슷한 글이 생성되어 cannibalization 발생 가능
- **피드백 루프 부재**: 성과 데이터 기반 개선 메커니즘이 없음

## 전략

**Phase A → Phase C 순차 접근**: 먼저 콘텐츠 품질을 대폭 높여 Google 신뢰 확보 → 이후 데이터 기반 피드백 루프 구축

> Phase B는 의도적으로 생략. 기술 SEO(sitemap, 내부 링크, Schema 등)는 이미 구현되어 있어 별도 phase 불필요.

---

## Phase A: 콘텐츠 품질 혁신

### A1. 프롬프트 고도화

**목표**: 자동 생성 콘텐츠가 수동 작성 콘텐츠와 구분하기 어려운 수준으로 품질 향상

**변경 사항**:

1. **프롬프트 A (IT 기초 용어)**: 최소 3000자. 다음 섹션 필수:
   - 정의와 핵심 개념 (what)
   - 왜 중요한지 (why) — 실무 시나리오 2개 이상
   - 작동 원리 (how) — 단계별 설명
   - 실무 적용 가이드 — 구체적 도구명, 설정값, 명령어
   - 비교표 또는 체크리스트 1개 이상
   - FAQ 3개 이상

2. **프롬프트 B (IT 트렌드/비교)**: 최소 3000자. 다음 섹션 필수:
   - 핵심 차이 요약 비교표 (글 상단)
   - 각 항목별 심층 비교 (기능, 성능, 비용, 사용성)
   - 실제 선택 기준 — "A를 선택해야 할 때 vs B를 선택해야 할 때"
   - 실무 마이그레이션/도입 시나리오

3. **프롬프트 C (트러블슈팅)**: 최소 3000자. 다음 섹션 필수:
   - 에러 메시지 원문 (영문 + 한글 설명)
   - 원인 분석 (3가지 이상 가능한 원인)
   - 단계별 해결 방법 — 코드 블록/명령어 포함
   - 예방 방법
   - 관련 에러 링크

4. **공통 지시**:
   - SERP 상위 결과를 참고하되 그대로 복사하지 말 것
   - 한국 IT 현장에서 실제 사용하는 용어와 도구 사용
   - `contoso.com` 등 가상 도메인 대신 설명 텍스트 사용
   - 인라인 출처: SERP 데이터에서 유용한 정보는 "[출처명](URL)" 형태로 삽입

**롤백 전략**: 기존 프롬프트를 `_v1` 접미사로 백업 보관. 프롬프트는 한 종류씩 순차적으로 교체하여 영향 범위를 최소화 (A → B → C 순서, 각 1주 간격).

**수정 파일**:
- `n8n/prompts/prompt_a_terminology.md` (기존 파일 개편)
- `n8n/prompts/prompt_b_comparison.md` (기존 파일 개편)
- `n8n/prompts/prompt_c_troubleshooting.md` (기존 파일 개편)
- `n8n/workflow_complete.json` (프롬프트 노드 jsCode 동기화)

### A2. 콘텐츠 길이/깊이 게이트

**목표**: 최소 품질 기준 미달 콘텐츠의 자동 발행 차단

**Pipeline A 변경** (`n8n/code_nodes/validate_structure.js` — 기존 구조 검증 노드에 추가):
```javascript
const MIN_CONTENT_LENGTH = 3000;
const contentBody = $input.item.json.content || '';
if (contentBody.length < MIN_CONTENT_LENGTH) {
  // status를 "검수필요"로 변경, 사유 = "본문 3000자 미만 (현재 N자)"
}
```

> "검수필요"는 Pipeline A에서 Sheets에 기록하는 상태값. Pipeline B의 `PostStatus` enum에는 포함되지 않으며, Pipeline B는 "발행대기" 상태만 조회하므로 "검수필요" 글은 자동으로 무시됨.

**Pipeline A 변경** (Haiku 검증 프롬프트 `n8n/prompts/prompt_d_verification.md`):
- 기존 4항목 + `is_in_depth` 추가 (5항목)
- `is_in_depth`: "본문이 주제에 대해 충분한 깊이로 설명하고 있는가? 단순 나열이 아닌 분석/설명이 포함되어 있는가? 비교표, 코드 블록, 또는 체크리스트가 1개 이상 포함되어 있는가?"

**Pipeline A 변경** (`n8n/code_nodes/parse_verification.js`):
```javascript
const isInDepth = typeof result.is_in_depth === "boolean" ? result.is_in_depth : true;

const passed = result.is_accurate === true
  && result.is_logical === true
  && isComplete === true
  && isUseful === true
  && isInDepth === true
  && qualityScore >= MIN_QUALITY_SCORE;
```

**Pipeline B 변경** (`src/domain/entities/post.py`):
```python
MIN_CONTENT_LENGTH = 3000

def is_publishable(self) -> bool:
    """True only when PENDING + quality body + sufficient length + quality_score."""
    return (
        self.status == PostStatus.PENDING
        and self.content is not None
        and self.content.has_body()       # guards against None body_markdown
        and len(self.content.body_markdown) >= MIN_CONTENT_LENGTH
        and self.quality_score >= 70
    )
```

> **None 안전성**: `has_body()` 가 `body_markdown`이 None이 아니고 비어있지 않음을 먼저 확인하므로, `len()` 호출은 항상 안전.

**기존 콘텐츠 마이그레이션**: 이 게이트는 Pipeline B 방어 계층. Pipeline A에서 이미 3000자 이상 생성을 강제하므로, 새로 생성되는 글은 기준을 충족. 기존 "발행대기" 상태의 짧은 글(3000자 미만)은 Pipeline B에서 is_publishable() = False로 건너뛰어지며, 수동으로 "검수필요"로 일괄 전환하는 마이그레이션 스크립트 제공.

**테스트 추가** (`tests/unit/domain/test_post_entity.py`):
- `test_is_publishable_content_too_short` — 3000자 미만 → False
- `test_is_publishable_content_sufficient` — 3000자 이상 → True

### A3. 중복 콘텐츠 탐지

**목표**: 기존 발행글과 유사한 콘텐츠 자동 생성 방지

**Pipeline A 변경** (신규 Code Node: `n8n/code_nodes/check_duplicate.js`):
- 워크플로우에서 콘텐츠 생성 후, 기존 "발행완료"/"발행대기" 글의 키워드 목록과 비교
- 키워드(A열) 기반 비교 (제목보다 안정적 — 한국어 조사 문제 회피)
- 70% 이상 겹침 시 `status = "검수필요"`, 사유 = "기존 글과 유사"

**구현 방식** (키워드 토큰 겹침 — V1 휴리스틱):
```javascript
function keywordOverlap(newKeyword, existingKeyword) {
  const tokensA = new Set(newKeyword.toLowerCase().split(/\s+/));
  const tokensB = new Set(existingKeyword.toLowerCase().split(/\s+/));
  if (tokensA.size < 2 || tokensB.size < 2) return 0; // 1-토큰 키워드는 건너뜀
  const intersection = [...tokensA].filter(t => tokensB.has(t));
  const smaller = Math.min(tokensA.size, tokensB.size);
  return smaller > 0 ? intersection.length / smaller : 0;
}
```

> **한계**: 한국어 조사("쿠버네티스를" vs "쿠버네티스는")는 다른 토큰으로 처리됨. V1에서는 키워드 컬럼(조사 없는 짧은 구문)을 비교 대상으로 사용하여 이 문제를 완화. 향후 형태소 분석기 도입 시 개선 가능.

**수정 파일**:
- `n8n/code_nodes/check_duplicate.js` (신규)
- `n8n/workflow_complete.json` (워크플로우에 노드 추가 — 콘텐츠 생성 후, 검증 전 위치)

### A4. 이미지 품질 향상

**목표**: 본문 내 시각적 구조 요소 강화

**프롬프트 변경** (A1 프롬프트 개편에 포함):
- 비교 글(프롬프트 B): 비교표를 마크다운 표로 필수 생성
- 가이드/용어 글(프롬프트 A): 프로세스 설명 시 Mermaid 다이어그램 권장 (이미 지원됨)
- 트러블슈팅 글(프롬프트 C): 단계별 해결 과정을 번호 목록 + 코드 블록으로 구조화

**Haiku 검증**: `is_in_depth` 검증 시 구조화 요소(표, 코드 블록, 체크리스트) 포함 여부도 평가 기준에 포함.

**코드 변경 없음**: 프롬프트 레벨에서 처리. 기존 마크다운 → HTML 변환 파이프라인 그대로 사용.

---

## Phase C: 데이터 기반 성장 엔진

> Phase A 적용 후 2~4주 효과 측정 이후 시작. Phase A 성과 측정은 기존 `CheckIndexingUseCase` + GSC 수동 확인으로 수행.

### C1. GSC 데이터 자동 수집

**목표**: Google Search Console 성과 데이터를 자동으로 수집하여 의사결정에 활용

**아키텍처**:
- `src/domain/ports/seo_port.py` — 기존 파일에 `GscDataPort` ABC 추가
- `src/infrastructure/seo/gsc_adapter.py` — Google Search Console API 어댑터
- `src/application/use_cases/collect_gsc_data.py` — CollectGscDataUseCase

**필요한 Port 인터페이스**:
```python
class GscDataPort(ABC):
    @abstractmethod
    def fetch_keyword_stats(self, site_url: str, days: int = 28) -> list[KeywordStat]: ...

    @abstractmethod
    def fetch_page_stats(self, site_url: str, days: int = 28) -> list[PageStat]: ...
```

**데이터 수집 범위**:
- 키워드별: 순위, 노출, 클릭, CTR (최근 28일)
- 페이지별: 순위, 노출, 클릭, CTR
- 일일 cron으로 수집 → Google Sheets "GSC성과" 시트에 저장

**Google Sheets 확장** (새 시트 또는 기존 시트 컬럼 추가):
- `gsc_impressions`: 노출 수
- `gsc_clicks`: 클릭 수
- `gsc_ctr`: CTR (%)
- `gsc_position`: 평균 순위
- `gsc_collected_at`: 수집 일시

**인증**: 기존 Google 서비스 계정에 Search Console 읽기 권한 추가

### C2. 성과 기반 콘텐츠 리프레시

**목표**: 순위 하락/정체 글을 자동으로 감지하고 개선

**대상 선정 기준**:
- 발행 후 30일 이상 경과
- GSC 순위 없음 (색인은 되었으나 노출 0) 또는 순위 하락 추세
- OR 노출은 있으나 CTR < 1%

**리프레시 프로세스**:
1. `IdentifyRefreshTargetsUseCase`: 대상 글 자동 선정
2. 기존 Post의 status를 "수정대기"로 변경 (기존 `mark_revision_pending()` 활용)
3. Pipeline A에 "리프레시 모드": 기존 본문 + 최신 SERP → 개선된 글 생성
4. 기존 `RevisePostsUseCase`로 Tistory 업데이트

**필요한 Port**: `GscDataPort` (C1에서 구현), `PostRepository` (기존)

**수정 파일**:
- `src/application/use_cases/identify_refresh_targets.py` (신규)
- `n8n/workflow_complete.json` (리프레시 모드 분기 추가)
- n8n 프롬프트에 "리프레시 지시" 추가

### C3. 제목/메타설명 최적화

**목표**: CTR이 낮은 글의 제목과 메타설명을 자동 개선

**대상 선정 기준**:
- GSC 노출 100+ / CTR < 2%
- 현재 제목/메타설명이 개선 가능한 경우

**프로세스**:
1. `OptimizeTitleUseCase`: 대상 글 선정 + n8n LLM 호출로 대안 제목 3개 생성
2. 사용자 승인 또는 자동 적용 (설정 가능)
3. Tistory 글 업데이트 (기존 수정 파이프라인 활용)
4. 변경 전/후 CTR 비교 (2주 후)

**필요한 Port**: `GscDataPort` (C1), `PostRepository` (기존). LLM 호출은 n8n 워크플로우를 통해 수행 (별도 LlmPort 불필요 — 기존 Pipeline A 인프라 재사용).

**수정 파일**:
- `src/application/use_cases/optimize_title.py` (신규)
- CLI: `--optimize-titles` 명령 추가

### C4. 주간 성과 리포트

**목표**: 사이트 성과를 주간 단위로 자동 요약

**리포트 내용**:
- 이번 주 신규 발행/리프레시 건수
- 신규 색인 수
- 총 노출/클릭/평균 CTR
- 상위 5개 키워드 (노출 기준)
- 상위 5개 성장 키워드 (전주 대비 순위 상승)
- 하위 5개 키워드 (순위 하락 → 리프레시 후보)

**필요한 Port**: `GscDataPort` (C1), `PostRepository` (기존), `NotificationPort` (기존 — 텍스트 메시지로 리포트 전송, 구조화된 리포트가 아닌 plain text 요약)

**수정 파일**:
- `src/application/use_cases/weekly_report.py` (신규)
- CLI: `--weekly-report` 명령 추가
- 기존 알림 시스템(Slack/Telegram) 활용

---

## 구현 순서

```
Phase A (2~3주)
├── A1: 프롬프트 고도화
│   ├── prompt_a_terminology.md 개편
│   ├── prompt_b_comparison.md 개편 (1주 후)
│   └── prompt_c_troubleshooting.md 개편 (2주 후)
├── A2: 길이/깊이 게이트
│   ├── Pipeline A: validate_structure.js 길이 검증
│   ├── Pipeline A: parse_verification.js is_in_depth 추가
│   ├── Pipeline A: prompt_d_verification.md 업데이트
│   ├── Pipeline B: Post 엔티티 MIN_CONTENT_LENGTH
│   ├── 기존 짧은 글 마이그레이션 스크립트
│   └── 테스트 추가
├── A3: 중복 탐지
│   ├── n8n Code Node: check_duplicate.js (신규)
│   └── 워크플로우에 노드 추가
└── A4: 이미지/구조화
    └── A1 프롬프트 개편에 포함

[2~4주 효과 측정 기간 — 기존 CheckIndexingUseCase + GSC 수동 확인]

Phase C (3~4주)
├── C1: GSC 데이터 수집
│   ├── seo_port.py에 GscDataPort 추가 (Domain Port)
│   ├── gsc_adapter.py (Infrastructure)
│   └── CollectGscDataUseCase
├── C2: 콘텐츠 리프레시
│   ├── IdentifyRefreshTargetsUseCase
│   └── Pipeline A 리프레시 모드
├── C3: 제목/메타 최적화
│   └── OptimizeTitleUseCase
└── C4: 주간 성과 리포트
    └── WeeklyReportUseCase
```

## 수정 파일 요약

| 파일 | Phase | 변경 내용 |
|------|-------|-----------|
| `n8n/prompts/prompt_a_terminology.md` | A1 | 프롬프트 전면 개편 (3000자+, E-E-A-T) |
| `n8n/prompts/prompt_b_comparison.md` | A1 | 프롬프트 전면 개편 |
| `n8n/prompts/prompt_c_troubleshooting.md` | A1 | 프롬프트 전면 개편 |
| `n8n/prompts/prompt_d_verification.md` | A2 | is_in_depth 항목 추가 |
| `n8n/code_nodes/validate_structure.js` | A2 | MIN_CONTENT_LENGTH 3000자 게이트 |
| `n8n/code_nodes/parse_verification.js` | A2 | is_in_depth 항목 추가 |
| `n8n/code_nodes/check_duplicate.js` | A3 | 신규 — 키워드 기반 중복 탐지 |
| `n8n/workflow_complete.json` | A2/A3 | 노드 동기화 |
| `src/domain/entities/post.py` | A2 | MIN_CONTENT_LENGTH 방어 게이트 |
| `tests/unit/domain/test_post_entity.py` | A2 | 길이 검증 테스트 2건 |
| `scripts/migrate_short_posts.py` | A2 | 기존 짧은 글 → "검수필요" 전환 |
| `src/domain/ports/seo_port.py` | C1 | GscDataPort ABC 추가 |
| `src/infrastructure/seo/gsc_adapter.py` | C1 | 신규 — GSC API 어댑터 |
| `src/application/use_cases/collect_gsc_data.py` | C1 | 신규 — GSC 수집 Use Case |
| `src/application/use_cases/identify_refresh_targets.py` | C2 | 신규 — 리프레시 대상 선정 |
| `src/application/use_cases/optimize_title.py` | C3 | 신규 — 제목 최적화 |
| `src/application/use_cases/weekly_report.py` | C4 | 신규 — 주간 리포트 |
| `src/interface/cli.py` | C1~C4 | 신규 CLI 명령 추가 |

## 성공 기준

| 지표 | Phase A 후 (4주) | Phase C 후 (8주) | 측정 방법 |
|------|------------------|------------------|-----------|
| 평균 콘텐츠 길이 | 3000자+ | 유지 | Sheets 데이터 |
| 검증 통과율 | 70%+ | 75%+ | n8n 로그 |
| 색인율 | 50%+ | 70%+ | CheckIndexingUseCase / GSC |
| 총 주간 노출 | 500+ | 2000+ | GSC |
| 평균 CTR | 1%+ | 2%+ | GSC |
| 일 유입 | 5+ | 20+ | GA4 |

## DDD 아키텍처 준수

모든 신규 코드는 기존 DDD 4-Layer 규칙 준수:
- Domain Port → Infrastructure Adapter 패턴
- Use Case는 Port 인터페이스만 참조
- `make validate-ddd` 0건 유지
- `make quality` 전체 통과
