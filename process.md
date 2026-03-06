# B2B IT 블로그 자동화 — 개발 프로세스 추적

> **문서 용도**: 실행 진행 추적 (마스터 플랜 `masterplan_v2.3.md`의 실행 로그)
> **최종 갱신**: 2026-03-06

---

## 현재 상태

| 항목 | 값 |
|------|---|
| **현재 Phase** | **Phase 7 진행 중** |
| **단위 테스트** | 201건 통과 |
| **Tistory 실발행** | 47건 성공 (최신: CORS 에러 원인과 해결 방법 → /226) |
| **ruff** | 0 errors |
| **콘텐츠 생성 모델** | Gemini 2.0 Flash (Phase 5.6에서 LLM_PROVIDER 추상화, `.env`로 전환 가능) |

---

## Phase 2: DDD 리팩토링 + TDD — 완료 (2026-02-28)

| # | 항목 | 상태 |
|---|------|------|
| 2.1 | Domain: Value Objects (PostStatus, Content, PublishResult, Credentials) | ✅ 완료 |
| 2.2 | Domain: Post Entity (상태 전이, is_publishable, 고스트 복구) | ✅ 완료 |
| 2.3 | Domain: Port 인터페이스 (PostRepository, BrowserPort) | ✅ 완료 |
| 2.4 | Application: Use Cases (PublishPosts, ResetStuck) | ✅ 완료 |
| 2.5 | Infra: InMemoryRepo (테스트용) | ✅ 완료 |
| 2.6 | 단위 테스트 전체 통과 (`pytest tests/ -v` → 66건 pass) | ✅ 완료 |

---

## Phase 2.5: 인프라 어댑터 + 단독 검증 — 진행 중

### 완료된 작업

| # | 항목 | 상태 | 비고 |
|---|------|------|------|
| 2.5.1 | google_sheets_repo.py → PostRepository 구현 | ✅ 완료 | |
| 2.5.2 | selenium_adapter.py → BrowserPort 구현 | ✅ 완료 | user_data_dir 지원 |
| 2.5.3 | kakao_auth.py → 로그인 로직 분리 | ✅ 완료 | **버그 수정 완료 (2026-02-28)** |
| 2.5.4 | tistory_editor.py → 에디터 조작 로직 분리 | ✅ 완료 | |
| 2.5.5 | dom_selectors.py → Fallback Chain 분리 | ✅ 완료 | |
| 2.5.6 | js_injector.py → safe_js_inject 분리 | ✅ 완료 | |
| 2.5.7 | cli.py → Composition Root 작성 | ✅ 완료 | user_data_dir 추가 |

### 2026-02-28: 카카오 로그인 버그 수정 (3건)

| 원인 | 수정 내용 | 파일 |
|------|----------|------|
| `_is_tistory_logged_in()`이 URL 전체에서 `"tistory.com"` 매칭 → OAuth redirect URL에서 false positive | `urlparse` hostname 기반 판별로 변경 | `kakao_auth.py` |
| 카카오 버튼 클릭 후 `time.sleep(3)` 고정 대기 → 리다이렉트 완료 전 URL 체크 | 최대 15초 URL 안정화 폴링으로 변경 | `kakao_auth.py` |
| `cli.py`에서 `user_data_dir` 미전달 → 매 실행마다 2FA 재요구 | `user_data_dir=".browser_data"` 추가 | `cli.py` |

추가 수정:
- `test_login.py`: 관리자 접근 체크에 `"auth/login" not in final_url` 조건 추가
- `.gitignore`: `.browser_data/` 추가

---

## 빌드 완료 진행 로그 (Phase 2 ~ 4)

### Step 1: 카카오 로그인 수정 검증 — ✅ 완료 (2026-02-28)

- 1-1. 카카오 로그인 + 관리자 접근: 성공
- 1-2. 쿠키 영속화 (2회차 2FA 없이 자동 로그인): 성공

### Step 2: 단독 발행 검증 — ✅ 완료 (2026-02-28)

- 2.5.9 카카오 로그인 성공
- 2.5.10 마크다운 모드 전환 성공
- 2.5.11 CodeMirror API 본문 주입 성공
- 2.5.12 임시저장 성공
- 2.5.13 시트 Status "발행완료" 업데이트 확인
- 2.5.14 고스트 복구 (발행중 → 발행대기 → 재발행) 성공
- 2.5.15 브라우저 프로세스 완전 종료 확인

버그 수정:
- URL 변경: `/manage/post/write` → `/manage/newpost` (API JSON 오류 수정)
- SB 컨텍스트 매니저 참조 유지 (GC로 인한 브라우저 즉시 종료 수정)
- DOM 셀렉터 전면 업데이트 (TinyMCE + CodeMirror 대응)

### Step 3: 통합 테스트 — ✅ 완료 (2026-02-28)

- GoogleSheets 통합 테스트 6건 통과
- Selenium 통합 테스트 3건 통과
- 전체 75건 통과, 2건 E2E 스킵

### (아래는 원본 Step 1~3 계획 — 참고용)

### ~~Step 1: 카카오 로그인 수정 검증 (즉시)~~

```bash
# 1-1. 실제 로그인 테스트 (headless=false로 육안 확인)
HEADLESS=false python3 test_login.py

# 1-2. 확인 사항:
#   - 카카오 로그인 페이지 도달 여부
#   - 2FA 승인 후 티스토리 리다이렉트 성공
#   - login_success.png 스크린샷 확인
#   - 관리자 페이지 접근 성공

# 1-3. 쿠키 영속화 테스트 (2회째 실행)
HEADLESS=false python3 test_login.py
#   - 2FA 없이 쿠키로 자동 로그인 확인
```

### Step 2: 단독 발행 검증 (Phase 2.5.8~2.5.15)

```bash
# 2-1. 시트에 더미 데이터 1건 입력 (Status=발행대기, content 필드 포함)
# 2-2. DDD 워커로 발행 테스트
HEADLESS=false python3 -m src.interface.cli

# 확인 사항:
# [ ] 2.5.9  카카오 로그인 성공
# [ ] 2.5.10 마크다운 모드 전환 성공
# [ ] 2.5.11 safe_js_inject() 본문 주입 성공
# [ ] 2.5.12 임시저장 또는 비공개 발행 성공
# [ ] 2.5.13 시트 Status "발행완료" 업데이트 확인
# [ ] 2.5.14 Self-Healing: 강제 종료 후 '발행중'→'발행대기' 롤백 확인
# [ ] 2.5.15 브라우저 프로세스 완전 종료 확인 (ps aux | grep chrome)
```

### Step 3: 통합 테스트 작성 및 실행 (Phase 2.5.16)

```bash
# 3-1. 통합 테스트 실행
python3 -m pytest tests/integration/ -v

# 3-2. 목표: 8건+ 통과
```

### Step 4: 파이프라인 A 구축 (Phase 3) — ✅ 완료 (2026-02-28)

| # | 항목 | 상태 | 비고 |
|---|------|------|------|
| 3.1 | n8n 워크플로우 조립 | ✅ 완료 | 13노드, workflow ID: 8nw9qRMqw3nAMB6m |
| 3.2 | 마스터 프롬프트 주입 | ✅ 완료 | A/B/C 프롬프트 전문 route_prompt 코드노드에 주입 |
| 3.3 | 교차 검증 로직 | ✅ 완료 | Haiku temp=0, parse_verification.js |
| 3.4 | JSON 파싱 에러 핸들링 | ✅ 완료 | parse_json.js + IF→검수필요 분기 |
| 3.5 | 파이프라인 A 단독 테스트 | ✅ 완료 | 전체 파이프라인 End-to-End 통과 |

#### 3.1~3.4 완료 세부 (2026-02-28)

- n8n Docker (1.76.1) 실행 확인
- 소유자 계정 생성: `admin@blog-automation.local` / `BlogAuto2026!`
- `workflow_complete.json` 생성: 5개 코드노드에 실제 JS 코드 주입, 3개 프롬프트 전문 포함
- n8n REST API로 워크플로우 임포트 (비활성 상태)

#### 3.5 단독 테스트 완료 세부 (2026-02-28)

- `.env` 설정 완료: SERPAPI_KEY, SHEET_ID, CLAUDE_API_KEY
- Google Sheets 서비스 계정 인증 (googleApi credential ID: k5evUG3OD0DA5vSR)
- Claude API: `claude-3-haiku-20240307` 모델 사용 (현재 API 키로 접근 가능한 모델)
- 수정 사항:
  - Google Sheets 노드: `serviceAccount` 인증 + `googleApi` credential 타입으로 변경
  - HTTP Request 노드: v4.2 형식 (`sendQuery` + `queryParameters`)으로 변경
  - Route Prompt 코드: 한국어 컬럼명 대응 + `$('Node Name')` 참조 방식
  - Parse JSON 코드: JSON 문자열 내 제어 문자 이스케이프 로직 추가
  - Sheets Update 노드: `matchingColumns` + 노드별 데이터 참조 수정
- 실행 결과: "API Gateway란" 키워드
  - 상태: `대기` → `발행대기` ✅
  - 제목: "API Gateway: 마이크로서비스 아키텍처를 위한 단일 진입점" ✅
  - 본문: 1,337자 마크다운 ✅
  - 프롬프트유형: A (용어) ✅
  - Haiku 검증: 통과 (is_accurate=true, is_logical=true) ✅
  - FAQ스키마: 3개 Q&A ✅
  - 참고자료: 외부 링크 목록 ✅

### Step 5: E2E 통합 테스트 (Phase 3.5) — ✅ 완료 (2026-02-28)

| # | 항목 | 상태 |
|---|------|------|
| 3.5.1 | 테스트 키워드 4건 입력 (용어×2 + 비교 + 에러) | ✅ 완료 |
| 3.5.2 | n8n 수동 트리거 → 4건 모두 "발행대기" 전이 | ✅ 완료 |
| 3.5.3 | 프롬프트 A/B/C 모두 정상 라우팅 | ✅ 완료 |
| 3.5.4 | Haiku 교차검증 4건 모두 통과 | ✅ 완료 |

#### E2E 테스트 세부 결과

| 키워드 | 유형 | 프롬프트 | 상태 | 본문 | 검증 |
|--------|------|----------|------|------|------|
| API Gateway란 | 용어 | A | 발행대기 | 1,282자 | ✅ |
| DHCP란 무엇인가 | 용어 | A | 발행대기 | 1,117자 | ✅ |
| Docker vs Kubernetes 비교 | 비교 | B | 발행대기 | 1,603자 | ✅ |
| SSH 접속 오류 해결 가이드 | 에러 | C | 발행대기 | 495자 | ✅ |

#### E2E 추가 수정 사항

- Sheets Read 노드: `filtersUI` 필터 추가 (상태=대기 조건)
- JSON 출력 스키마: 메타데이터 필드 먼저, content 필드를 마지막으로 배치 (토큰 제한 대응)
- Parse JSON: 이스케이프된 백슬래시 처리 + 잘린 JSON 복구 로직 추가
- 시스템 프롬프트: JSON 형식 안전 지시 추가 (줄바꿈/따옴표 이스케이프 명시)

### Step 6: Go-Live (Phase 4) — ✅ 완료 (2026-02-28)

| # | 항목 | 상태 | 비고 |
|---|------|------|------|
| 4.1 | n8n Schedule Trigger 활성화 (01:00 AM) | ✅ 완료 | workflow active=true |
| 4.2 | Cronjob 등록: `python3 -m src.interface.cli` (09:00 AM) | ✅ 완료 | `run_pipeline_b.sh` + crontab |
| 4.3 | 수동 E2E 검증 (Pipeline A→B 전체 흐름) | ✅ 완료 | IAM이란 무엇인가 → 발행완료 |
| 4.5 | 레거시 파일 정리 → `legacy/` + `screenshots/` | ✅ 완료 | test_login.py + PNG 12개 |

#### Go-Live 완료 사항
- n8n 워크플로우 활성화: `Blog Automation Pipeline A — Content Generation`
- Schedule Trigger: 매일 01:00 AM (Asia/Seoul)
- 테스트 워크플로우 정리 완료 (2개 삭제)
- 최종 워크플로우 백업: `n8n/workflow_complete.json`

### Step 7: 키워드 캘린더 임포트 — ✅ 완료 (2026-02-28)

| # | 항목 | 상태 | 비고 |
|---|------|------|------|
| 7.1 | 사용자 키워드 캘린더 .xlsx 공유 | ✅ 완료 | 서비스 계정에 공유 |
| 7.2 | .xlsx API 비호환 → Pipeline A 시트에 직접 입력 방식 결정 | ✅ 완료 | FAILED_PRECONDITION 에러 |
| 7.3 | 기존 테스트 데이터 삭제 (34행) | ✅ 완료 | gspread `batch_update` deleteDimension |
| 7.4 | 30개 B2B IT 키워드 입력 | ✅ 완료 | 용어 14건, 비교 10건, 에러 6건 |
| 7.5 | Pipeline A 워크플로우 재활성화 | ✅ 완료 | active=true |

#### 키워드 분포
- **용어 (14건)**: IAM, 제로트러스트, MFA, SD-WAN, CI/CD, Terraform, SIEM, Prometheus+Grafana, 마이크로서비스, Redis, WAF, DDoS, GitOps, 서비스메시
- **비교 (10건)**: Azure AD vs Okta, SAML vs OAuth, AWS vs Azure vs GCP, Jenkins vs GitHub Actions, Ansible vs Terraform, Splunk vs ELK, gRPC vs REST, PostgreSQL vs MySQL, Nginx vs Apache, Kafka vs RabbitMQ
- **에러 (6건)**: VPN 연결 오류, K8s CrashLoopBackOff, SSL 인증서 오류, DNS 조회 실패, Docker 빌드 실패, 로드밸런서 설정 오류

---

## Phase 5 사전작업: Pipeline B 발행 버그 수정 — 🔧 진행 중 (2026-02-28)

> **발견**: Phase 5 수동 검증 중 발견. Pipeline B가 글을 발행하지만 **제목만 입력**되고 **본문과 태그가 누락**됨.

### 발견된 버그 (3건)

| # | 버그 | 원인 | 수정 상태 |
|---|------|------|-----------|
| B1 | 공개발행 안 됨 (임시저장만) | `tistory_editor.py`가 `SAVE_BUTTON_SELECTORS`만 사용, `PUBLISH_BUTTON_SELECTORS` 미사용 | ✅ 수정 완료 |
| B2 | 본문 주입 실패 (제목만 입력됨) | 마크다운 모드 전환 시 `window.confirm()` 팝업 미처리 → 모드 전환 실패 → CodeMirror 미활성 | 🔧 수정 중 |
| B3 | 태그 미입력 | `PostContent`에 tags 필드 없음 + 에디터에 태그 입력 로직 없음 | ✅ 코드 수정 완료 (검증 대기) |

### B1 수정 내역 (공개발행)
- `dom_selectors.py`: `PUBLISH_CONFIRM_SELECTORS` 추가 (발행 레이어 내 확인 버튼)
- `tistory_editor.py`: 2단계 발행 로직 구현
  - Step 1: 임시저장 (`SAVE_BUTTON_SELECTORS`) → 내용 서버 저장
  - Step 2: 완료 버튼 (`PUBLISH_BUTTON_SELECTORS`) → 발행 설정 레이어 열기
  - Step 3: 공개발행 확인 (`PUBLISH_CONFIRM_SELECTORS`) → 최종 발행
- 결과: URL이 `/manage/posts/`로 리다이렉트됨 → 발행은 성공하나 본문 비어있음

### B2 수정 내역 (본문 주입 실패 — 핵심 버그)

**문제 흐름**:
1. 에디터 페이지 열기 → 기본모드(WYSIWYG)
2. 마크다운 모드 전환 클릭 시 `window.confirm()` 팝업 발생:
   - "작성 모드를 변경하시겠습니까? 현재 서식이 유지되지 않을 수 있습니다."
   - 취소 / 확인 버튼
3. 이 팝업이 **네이티브 브라우저 `window.confirm()`** → DOM에 없어서 JS로 찾을 수 없음
4. 팝업 미처리 → 모드 전환 미완료 → CodeMirror 미활성화
5. `.CodeMirror` 셀렉터가 다른 용도의 CodeMirror를 잡아 `setValue()` 성공 리턴
6. 실제 에디터 콘텐츠는 비어있는 상태로 발행됨

**시도한 수정 (4회)**:
| # | 시도 | 결과 |
|---|------|------|
| 1 | `sb.accept_alert(timeout=2)` | ❌ SeleniumBase alert 핸들러가 confirm 못 잡음 |
| 2 | CSS 셀렉터 (`MODE_CONFIRM_SELECTORS`) | ❌ DOM에 없는 네이티브 팝업이라 셀렉터 무효 |
| 3 | JS로 페이지 전체에서 "확인" 텍스트 버튼 탐색 | ❌ 네이티브 confirm은 DOM에 없음 |
| 4 | `window.confirm = function() { return true; }` | ⏳ 검증 대기 |

**현재 적용된 코드** (시도 4):
```python
# publish_post() 내, 마크다운 전환 전에:
sb.execute_script("window.confirm = function() { return true; };")
```
이 방법은 `window.confirm()` 호출을 가로채서 자동으로 `true` 반환 → 팝업 없이 모드 전환 완료 예상.

### B3 수정 내역 (태그 입력)
- `post_content.py`: `tags: str = ""` 필드 + `tag_list()` 메서드 추가
- `google_sheets_repo.py`: 시트 G열(태그) 읽어서 `PostContent.tags`에 저장
- `dom_selectors.py`: `TAG_INPUT_SELECTORS = ["#tagText"]` (이미 존재했음)
- `tistory_editor.py`: `_input_tags()` 함수 추가 — 쉼표 구분 태그를 개별 입력

### 버그 수정 검증 결과 — ✅ 완료 (2026-02-28)

- [x] B2 검증: `window.confirm` 오버라이드로 마크다운 전환 팝업 우회 → **성공**
- [x] B2 검증: 본문이 실제 발행 글에 포함됨 → **성공** (CodeMirror 2253자 주입, 실제 글에서 렌더링 확인)
- [x] B3 검증: 태그 입력 `sb.type(tag_sel, tag + "\n")` → **성공** (글 보기에서 5개 태그 표시 확인)
- [x] CodeMirror `setValue()` + `save()` + `#editor-tistory` 동기화 → **정상 동작**
- [x] `PUBLISH_CONFIRM_SELECTORS`: `#publish-btn` → **정상** (JS fallback 추가)
- [x] 발행 후 URL: `_extract_published_url()` 추가 → 블로그 도메인 필터로 실제 URL 추출 (`/175` ~ `/181`)
- [ ] `user_data_dir` 마크다운 모드 유지: 테스트 중 비발생 (추가 관찰 필요)

### 발행 결과 (6건, 비공개)

| Row | 키워드 | URL | 본문 | 태그 |
|-----|--------|-----|------|------|
| 2 | IAM이란 무엇인가 | /181 | 1,483자 | IAM, 보안, AWS IAM, 권한관리, 클라우드 |
| 3 | Azure AD vs Okta 비교 | /176 | 1,590자 | Azure AD, Okta, SSO, IAM, 클라우드 보안 |
| 4 | SAML vs OAuth 차이 | /177 | 1,550자 | SAML, OAuth, 인증 프로토콜, SSO, 보안 |
| 5 | 제로 트러스트 보안 모델이란 | /178 | 1,418자 | 제로트러스트, 보안, ZTA, 네트워크 보안, 클라우드 |
| 6 | MFA 설정 방법 가이드 | /179 | 1,451자 | MFA, 다단계인증, 2FA, 보안, AWS |
| 7 | VPN 연결 오류 해결 | /180 | 558자 | VPN, 네트워크, 오류해결, 원격접속, 보안 |

### 추가 수정 사항 (2026-02-28)

| 파일 | 변경 |
|------|------|
| `tistory_editor.py` | `_extract_published_url()` 추가 — 블로그 도메인 전용 URL 필터 |
| `tistory_editor.py` | `_input_tags()` 개선 — `sb.type(sel, tag + "\n")` 방식 |
| `tistory_editor.py` | 발행 확인 버튼 JS fallback 추가 (timeout 5→10초 + JS 클릭) |
| `tistory_editor.py` | `from __future__ import annotations` 추가 (Python 3.9 호환) |
| `google_sheets_repo.py` | `faq_schema` 필드 전달 누락 수정 |

### 수정 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `src/domain/value_objects/post_content.py` | `tags` 필드 + `tag_list()` 메서드 추가 |
| `src/infrastructure/browser/dom_selectors.py` | `PUBLISH_CONFIRM_SELECTORS`, `MODE_CONFIRM_SELECTORS` 추가 |
| `src/infrastructure/browser/tistory_editor.py` | 전면 개선: 2단계 발행, 팝업 처리, 태그 입력, CodeMirror 주입 강화 |
| `src/infrastructure/persistence/google_sheets_repo.py` | `tags` 필드 읽기 추가 |

---

## Phase 5.5: 콘텐츠 품질 강화 — ✅ 완료 (2026-02-28)

> **배경**: E2E 테스트 결과 본문 품질이 목표에 미달. 근본 원인 5가지 해결.

### 콘텐츠 품질 분석 결과

| 키워드 | 유형 | 본문 길이 | 목표 | 판정 |
|--------|------|----------|------|------|
| API Gateway란 | A | 1,282자 | 1,500~2,500 | ❌ 미달 |
| DHCP란 | A | 1,117자 | 1,500~2,500 | ❌ 미달 |
| Docker vs Kubernetes | B | 1,603자 | 2,000~3,000 | ❌ 미달 |
| SSH 접속 오류 해결 | C | 495자 | 2,000~3,500 | ❌ 심각 미달 |

### 근본 원인 5가지

| # | 원인 | 위치 | 영향 |
|---|------|------|------|
| 1 | 콘텐츠 생성에 Haiku 모델 사용 | `workflow_complete.json:151` | Sonnet 대비 짧고 얕은 출력 |
| 2 | "2000자 이내" 상한 지시 | 3개 프롬프트 content 필드 | 모델이 짧게 작성하도록 유도 |
| 3 | 본문 길이 검증 없음 | `parse_json.js` | 495자도 통과 |
| 4 | SERP 데이터 5개 스니펫만 사용 | `route_prompt.js` | PAA/관련검색/KG 미활용 |
| 5 | 검증이 정확성+논리만 확인 | `prompt_d_verification.md` | 짧고 피상적이어도 통과 |

### 작업 항목 + 상태

| # | 작업 | 수정 파일 | 상태 |
|---|------|----------|------|
| 1 | 모델 Haiku→Sonnet 4.5, max_tokens 8192 | `workflow_complete.json` | ✅ |
| 2 | 본문 길이 검증 (A:1500, B/C:2000) | `parse_json.js`, `workflow_complete.json` | ✅ |
| 3 | 프롬프트 A 재설계 (섹션별 최소, SERP 활용, 체크리스트) | `prompt_a_terminology.md`, `workflow_complete.json` | ✅ |
| 4 | 프롬프트 B 재설계 | `prompt_b_comparison.md`, `workflow_complete.json` | ✅ |
| 5 | 프롬프트 C 재설계 | `prompt_c_troubleshooting.md`, `workflow_complete.json` | ✅ |
| 6 | "2000자 이내" → "최소 N자 이상" | 3개 프롬프트 + `workflow_complete.json` | ✅ |
| 7 | IMAGE_PLACEHOLDER → "텍스트로만 설명" | 3개 프롬프트 + `workflow_complete.json` | ✅ |
| 8 | SERP 구조화 파싱 (parse_serp.js 신규) | `parse_serp.js`, `workflow_complete.json` | ✅ |
| 9 | route_prompt.js SERP 연결 변경 | `route_prompt.js`, `workflow_complete.json` | ✅ |
| 10 | 검증 4항목 확장 (is_complete, is_useful, quality_score) | `prompt_d_verification.md`, `workflow_complete.json` | ✅ |
| 11 | parse_verification.js 4항목 판정 | `parse_verification.js`, `workflow_complete.json` | ✅ |
| 12 | 마크다운 구조 검증 (validate_structure.js 신규) | `validate_structure.js`, `workflow_complete.json` | ✅ |
| 13 | FAQ LD+JSON 자동 주입 | `post_content.py`, `tistory_editor.py` | ✅ |
| 14 | internal_link_keywords 굵게 지시 | 3개 프롬프트 | ✅ |
| 15 | 문서 업데이트 (masterplan, prosess) | `masterplan_v2.3.md`, `process.md` | ✅ |

### 수정 파일 요약 (13개)

| 파일 | 변경 유형 |
|------|----------|
| `n8n/workflow_complete.json` | 모델 변경, max_tokens, Parse SERP 노드 추가, Validate Structure 노드 추가, 프롬프트 업데이트, 검증 확장 |
| `n8n/prompts/prompt_a_terminology.md` | 섹션별 최소, SERP 활용, 체크리스트, IMAGE_PLACEHOLDER 제거 |
| `n8n/prompts/prompt_b_comparison.md` | 동일 |
| `n8n/prompts/prompt_c_troubleshooting.md` | 동일 |
| `n8n/prompts/prompt_d_verification.md` | 4항목 확장, quality_score 추가 |
| `n8n/code_nodes/parse_json.js` | 본문 길이 검증 추가 |
| `n8n/code_nodes/parse_serp.js` | **신규** — SERP 구조화 파싱 |
| `n8n/code_nodes/validate_structure.js` | **신규** — 마크다운 구조 검증 |
| `n8n/code_nodes/parse_verification.js` | 4항목 판정 로직 |
| `n8n/code_nodes/route_prompt.js` | SERP 텍스트 연결 방식 변경 |
| `src/domain/value_objects/post_content.py` | faq_ld_json() 메서드 추가 |
| `src/infrastructure/browser/tistory_editor.py` | FAQ LD+JSON 주입 |
| `masterplan_v2.3.md` | Phase 5.5 문서화 |

### 목표 지표

| 지표 | 이전 | 목표 |
|------|------|------|
| A타입 평균 길이 | 1,200자 | 2,000자+ |
| B타입 평균 길이 | 1,600자 | 2,500자+ |
| C타입 평균 길이 | 495자 | 2,500자+ |
| H2 헤딩 수 | 2~3 | 4~5 |
| 테이블 포함률 | ~50% | 100% |
| 코드블록 (C타입) | 0~1 | 3+ |

---

## Phase 5.6: LLM Provider 추상화 + 파이프라인 안정화 — ✅ 완료 (2026-02-28)

> **배경**: LLM 제공자(Claude ↔ Gemini) 전환 시 워크플로우 JSON의 6곳 이상을 수동 수정해야 하는 문제.
> `.env`의 `LLM_PROVIDER=gemini` 한 줄만 변경하면 워크플로우 수정 없이 전환되도록 추상화.

### 계획 대비 실제 구현 체크

| Step | 계획 | 실제 | 상태 | 차이점 |
|------|------|------|------|--------|
| 1 | `build_llm_request.js` 신규 작성 | 계획대로 구현 | ✅ | 없음 — PROVIDERS 맵, purpose별 opts 분기 |
| 2 | HTTP 노드를 Generic으로 변경 (동적 URL/headers/body) | 계획대로 변경 | ✅ | 없음 — `={{ $json._llm_url }}` 방식 |
| 3 | `normalize_llm_response.js` 신규 작성 | 계획대로 구현 | ✅ | 없음 — Gemini/Claude 응답 분기 |
| 4 | Parse 노드 입력을 `$input.item.json.text`로 단순화 | 계획대로 변경 | ✅ | 없음 |
| 5 | Verification용 Build Request 배치 | 계획대로 구현 | ✅ | 없음 — 별도 Code Node로 검증 요청 생성 |
| 6 | 워크플로우 연결 변경 (Content Gen + Verify 경로) | 계획대로 변경 | ✅ | 없음 |
| 7 | `.env`에 `LLM_PROVIDER=gemini` 추가 | 계획대로 추가 | ✅ | 없음 |
| 8 | 노드명 provider-agnostic으로 정리 | 계획대로 변경 | ✅ | 없음 |

### 계획 외 추가 작업 (파이프라인 테스트 중 발견)

| # | 문제 | 원인 | 수정 | 파일 |
|---|------|------|------|------|
| E1 | `Bad control character in string literal` | Gemini가 JSON 내 raw newline 생성 | 제어 문자 이스케이프 | `parse_json.js` |
| E2 | `Unterminated string in JSON` | `\`\`\`json` 추출 시 lazy regex가 본문 내 `\`\`\`bash` 에서 조기 종료 | `indexOf`/`lastIndexOf` 기반 추출로 변경 | `parse_json.js` |
| E3 | `Expected ',' or ']' after array element` | 누락된 쉼표, 후행 쉼표 등 구조적 JSON 오류 | `repairAndParse()` 도입 | `parse_json.js` |
| E4 | `Expected ',' or '}' after property value` (1차) | bash 명령어 내 `\g`, `\e` 등 유효하지 않은 이스케이프 시퀀스 | 유효하지 않은 이스케이프 → 이중 이스케이프 (`\g` → `\\g`) | `parse_json.js` |
| E5 | `Expected ',' or '}' after property value` (2차) | YAML 코드블록 내 `memory: "512Mi"` — 이스케이프되지 않은 `"` | **Lenient 재귀 하강 JSON 파서** (`repairJson()`) 구축 | `parse_json.js` |
| E6 | Google Sheets `50000 characters in a single cell` | `Haiku검증` 컬럼에 LLM 원시 응답 전체 저장 | `.item.json.verification`만 저장하도록 변경 | `workflow_complete.json` |

### E5: Lenient JSON 파서 (`repairJson`) 상세

LLM이 생성하는 JSON의 공통 문제를 자동 복구하는 재귀 하강 파서:

```
parse 전략: 직접 JSON.parse → 실패 시 repairJson 후 재파싱 → 실패 시 에러
```

**복구 항목**:
- 문자열 내 이스케이프되지 않은 `"` (YAML, 코드블록 등) → peek-ahead 휴리스틱으로 구조적/콘텐츠 `"` 판별
  - 다음 비공백 문자가 `,` `]` `}` `:` 또는 EOF → 구조적 종료
  - 다음이 `"` → 그 뒤에 `:` 가 있으면 객체 키 시작 → 구조적 종료
  - 그 외 → 콘텐츠 내 `"` → `\"` 로 이스케이프
- 제어 문자 (raw newline → `\n`, tab → `\t`, CR → `\r`)
- 유효하지 않은 이스케이프 시퀀스 (`\g` → `\\g`)
- 누락된 쉼표 (객체/배열 요소 사이)

### 전체 파이프라인 테스트 결과

```
실행 결과: Exit code 0, 26 nodes success, 0 errors
처리 건수: 14건 (대기 → 발행대기 전이 완료)
프롬프트 유형: A(용어) 14건, B(비교) 10건, C(에러) 6건 — 전체 정상 라우팅
Haiku 교차검증: 14건 모두 통과
```

### 신규 생성 파일

| 파일 | 설명 |
|------|------|
| `n8n/code_nodes/build_llm_request.js` | provider별 LLM 요청 빌더 (2,204B) |
| `n8n/code_nodes/normalize_llm_response.js` | provider별 응답 정규화 (713B) |

### 수정된 파일

| 파일 | 변경 내용 |
|------|----------|
| `n8n/code_nodes/parse_json.js` | 입력 경로 단순화 (`text`) + lenient JSON 파서 도입 (6,662B) |
| `n8n/code_nodes/parse_verification.js` | 입력 경로 단순화 + `sanitizeJsonStrings()` 추가 (3,314B) |
| `n8n/workflow_complete.json` | 노드 4개 추가 (Build Request ×2, Normalize ×2), HTTP 노드 Generic 변경, connections 재구성, Haiku검증 셀 수정 |
| `.env` | `LLM_PROVIDER=gemini` 섹션 추가 |

### 의사결정 로그

| 결정 | 근거 |
|------|------|
| Code Node 기반 추상화 (n8n 내장 switch 대신) | n8n 표현식만으로는 복잡한 body 구조 분기 불가, JS 코드로 완전 제어 가능 |
| Lenient 재귀 하강 파서 도입 | 단순 regex/state-machine으로는 `"` 구별 불가 — peek-ahead 컨텍스트 필요 |
| `indexOf`/`lastIndexOf` 기반 JSON 블록 추출 | 본문 내 `\`\`\`bash` 등 코드 펜스가 lazy regex 매칭을 교란 |
| `.verification` 서브객체만 Sheets 저장 | LLM 원시 응답 50K+ → Google Sheets 셀 50K 제한 초과 |
| Gemini로 LLM_PROVIDER 기본값 설정 | 비용 효율 (Gemini Flash 무료 tier) + Claude API 키 불필요 |

---

## Phase 5: 운영 안정화 + SEO 기반 구축 — 🔧 진행 중

> **기간**: W1~2 (2026-03-01 ~ 2026-03-14)
> **목표**: 자동 파이프라인 안정 운영 확인 + 검색엔진 등록 완료

| # | 항목 | 상태 | 완료일 |
|---|------|------|--------|
| 5.1 | 자동 실행 검증 — Schedule Trigger 확인 + 대기 10건 전환 | ✅ 설정완료 | 2026-02-28 |
| 5.2 | 로그 점검 체계 구축 (`check_status.sh`, `check_last_run.sh`) | ✅ 완료 | 2026-02-28 |
| 5.3 | Google Search Console 등록 + sitemap.xml 제출 | 📋 가이드 작성 | |
| 5.4 | Google Analytics 4 추적 코드 삽입 | 📋 가이드 작성 | |
| 5.5 | 네이버 서치어드바이저 등록 + robots.txt 확인 | 📋 가이드 작성 | |
| 5.6 | 첫 5건 수동 색인 요청 (URL 검사 → 색인 요청) | 📋 가이드 작성 | |
| 5.7 | 성과 대시보드 — KPI 추적 시트 | ✅ 완료 | 2026-02-28 |
| 5.8 | 발행 품질 검수 — 20건 자동 검수 + 태그 입력 | ✅ 완료 | 2026-02-28 |
| 5.9 | 레거시 코드 정리 (`legacy/`, `screenshots/`, 테스트 워크플로우) | ✅ 완료 | 2026-02-28 |

### 5.1 자동 실행 검증 세부

- Schedule Trigger: `0 1 * * *` (01:00 AM KST) ✅
- 타임존: `Asia/Seoul` (GENERIC_TIMEZONE + TZ) ✅
- 워크플로우 활성: `active=true` ✅
- Pipeline B crontab: `0 9 * * *` ✅
- 보류 10건 → 대기 전환 완료 (오늘 밤 01:00 AM 자동 실행 대상)
- **2일 연속 확인**: 03/01~02 아침 `./check_last_run.sh`로 결과 검증 필요

### 5.2 로그 점검 도구

| 스크립트 | 용도 |
|----------|------|
| `check_status.sh` | 전체 파이프라인 상태 점검 (Docker, 워크플로우, 실행이력, Sheets, 리소스) |
| `check_last_run.sh` | 최근 실행 결과 상세 (시간, 소요, Sheets 변동) |

### 5.7 KPI 대시보드

- Google Sheets에 "KPI 대시보드" 탭 생성
- 주간 KPI 기록 구조 (W1~W8)
- Go/No-Go 게이트 추적 (색인 10건, CTR 1%, 일유입 10명)
- 콘텐츠 품질 지표 (본문 길이, H2 수, 테이블/코드블록 포함률)

### 5.8 발행 품질 검수 결과

| 구분 | 건수 | 평균본문 | 이슈 |
|------|------|---------|------|
| 발행완료 (구 파이프라인) | 6건 | 1,342자 | 길이 부족, 메타 짧음 (Phase 4 생성물) |
| 발행대기 (신 파이프라인) | 14건 | 4,639자 | ✅ 품질 양호 |

**수정 사항**:
- 프롬프트 A/B/C에 `tags` 필드 추가 (향후 자동 생성)
- Sheets Update 노드에 `태그`, `생성일시`, `카테고리` 매핑 추가
- 기존 14건에 태그 수동 입력 완료

### 5.9 정리 내역

| 삭제 항목 | 내용 |
|----------|------|
| `legacy/` | test_login.py (디버그 잔여물) |
| `screenshots/` | 디버그 스크린샷 12개 (~2MB) |
| LLM Abstraction Test 워크플로우 | n8n 테스트용 워크플로우 삭제 |
| n8n 실행 이력 8건 | 디버깅 중 실패 이력 정리 (최근 3건 유지) |
| `.gitignore` | `legacy/` 추가 |

### 5.10 MD→HTML 변환 버그 수정 (2026-03-01)

**증상**: 발행된 글(`/182`)에서 HTML 태그 0개, 마크다운 원문이 Text Node로 그대로 노출
**근본 원인**: CodeMirror `setValue()`로 마크다운 주입 → 티스토리 에디터가 MD→HTML 변환을 수행하지 않음 → 서버에 raw markdown 저장

**수정 방향**: 방향 A — Python 측 MD→HTML 변환 후 WYSIWYG 모드(TinyMCE) 주입

| 변경 파일 | 내용 |
|----------|------|
| `tistory_editor.py` | `convert_markdown_to_html()`, `validate_html()`, `_inject_html_content()`, `_wait_for_wysiwyg_editor()` 추가. 마크다운 모드 전환 비활성화 |
| `dom_selectors.py` | `TINYMCE_IFRAME_SELECTORS` 활용 |
| `pyproject.toml` | `markdown>=3.5` 의존성 추가 |
| `tests/unit/infrastructure/test_markdown_to_html.py` | 21개 테스트 추가 (변환 11 + 검증 10) |

**검증 항목**:
- `<h2>/<h3>` 태그 존재
- `<p>` 태그 존재
- 잔여 마크다운 문법(`## `, `**`, `|---|`) 미포함 (`<pre>/<code>` 블록 제외)

**테스트 결과**: 95건 전체 통과 (기존 74 + 신규 21)

### 5.3~5.6 SEO 등록 가이드

`SEO_SETUP_GUIDE.md` 작성 완료. 주요 발견:
- 발행완료 6건이 **비공개** 상태 → 공개 전환 필요
- robots.txt: 정상 (네이버봇 차단 없음)
- sitemap.xml: Tistory 자동 생성, ~154번까지 (비공개 글 미포함)
- RSS: 8건 (비공개 글 미포함)

### 5.1 실행 방법
```bash
# 다음 날 아침 로그 확인
tail -50 /var/log/blog-publisher.log
# n8n 실행 이력 확인
curl -s http://localhost:5678/api/v1/executions -H "X-N8N-API-KEY: ..." | jq '.data[:3]'
```

### 5.3 Search Console 등록 절차
1. https://search.google.com/search-console 접속
2. 속성 추가 → `https://kimsanghyeon.tistory.com`
3. HTML 태그 또는 DNS 방식으로 소유권 확인
4. sitemap.xml 제출: `https://kimsanghyeon.tistory.com/sitemap.xml`
5. RSS 피드 제출: `https://kimsanghyeon.tistory.com/rss`

### 5.5 네이버 서치어드바이저 등록 절차
1. https://searchadvisor.naver.com 접속
2. 사이트 등록 → 소유 확인 (HTML 태그)
3. robots.txt에 네이버 크롤러 허용 확인
4. 사이트맵 제출

---

## Phase 5.7: 이미지 삽입 + HTML 변환 파이프라인 — ✅ 완료 (2026-03-01)

> **목표**: Unsplash 이미지 자동 삽입 + codehilite/TOC 확장 + 검증 강화

### 변경 사항 체크리스트

| # | 항목 | 상태 |
|---|------|------|
| 1 | `pyproject.toml` — `Pygments>=2.17` 의존성 추가 | ✅ |
| 2 | 프롬프트 A/B/C — 이미지 금지 제거, IMAGE 마커 지시 추가 | ✅ |
| 3 | `inject_images.js` — Unsplash 이미지 자동 삽입 Code Node (`this.helpers.httpRequest`) | ✅ |
| 4 | `tistory_editor.py` — codehilite + toc 확장, lazy loading, validate_html 강화 | ✅ |
| 5 | `validate_structure.js` — IMAGE 마커 잔류 검사 + image_count | ✅ |
| 6 | `workflow_complete.json` — Inject Images 노드 추가 + 연결 재배선 | ✅ |
| 7 | `test_markdown_to_html.py` — 신규 테스트 10건 추가 | ✅ |

### 설계 결정

| 결정 | 근거 |
|------|------|
| `codehilite` noclasses=True | TinyMCE iframe에서 외부 CSS 불필요, 인라인 스타일 직접 생성 |
| `toc` toc_depth="2-3" | H2/H3만 목차에 포함, 너무 깊은 계층 방지 |
| IMAGE 마커 → Unsplash API | 무료 tier, attribution 자동 포함, landscape 기본 |
| H2 fallback (마커 미발견 시) | LLM이 마커를 빠뜨려도 상위 4개 H2 기반으로 자동 삽입 |
| lazy loading | Core Web Vitals (LCP) 개선, `loading="lazy"` 자동 삽입 |
| validate_html 본문 길이 1,500자 | 기존에 495자 본문도 통과하는 문제 해결 |
| IMAGE 마커 잔류 → hard fail | inject_images.js 이후 잔류하면 파이프라인 오류 |
| `this.helpers.httpRequest` 사용 | n8n Code Node 샌드박스가 `fetch`/`require('https')` 미노출, `this.helpers`만 사용 가능 |
| Sheets Update → `$('Inject Images')` 참조 | 이미지 삽입 후 content를 저장해야 하므로 Inject Images 노드 출력 참조 |
| `extractSearchKeyword()` 영문 추출 | Unsplash는 영문 검색이 효과적, 한국어 H2에서 영문 단어 추출 후 검색 |

### 수정 파일 목록

| 파일 | 변경 유형 |
|------|----------|
| `pyproject.toml` | 의존성 추가 |
| `n8n/prompts/prompt_a_terminology.md` | 이미지 마커 규칙 추가 |
| `n8n/prompts/prompt_b_comparison.md` | 동일 |
| `n8n/prompts/prompt_c_troubleshooting.md` | 동일 |
| `n8n/code_nodes/inject_images.js` | 신규 생성 |
| `n8n/code_nodes/validate_structure.js` | 검증 항목 추가 |
| `n8n/workflow_complete.json` | 노드 추가 + 연결 재배선 |
| `src/infrastructure/browser/tistory_editor.py` | codehilite/toc/lazy loading/validate 강화 |
| `tests/unit/infrastructure/test_markdown_to_html.py` | 신규 테스트 10건 |

### E2E 테스트 중 발견/수정한 버그

| # | 문제 | 원인 | 수정 |
|---|------|------|------|
| E1 | `images_injected: 0` (Inject Images 실행 9ms) | n8n Code Node 샌드박스에서 `fetch` 미노출 (`fetch is not defined`) | `fetch` → `this.helpers.httpRequest()` 변경 |
| E2 | 이미지 삽입 성공하나 Sheets에 이미지 미반영 | `Sheets Update` 노드가 `$('Parse JSON Response')` (이미지 삽입 전) 참조 | `$('Inject Images')` 참조로 변경 |
| E3 | H2 fallback으로 Unsplash 검색 시 결과 0건 | 한국어 H2("개요", "Jenkins 상세")를 그대로 검색 → Unsplash는 영문 검색만 유효 | `extractSearchKeyword()` 추가: H2에서 영문 추출, 없으면 글 제목 영문 fallback |

### E2E 파이프라인 테스트 결과

#### 테스트 1: 용어 유형

```
키워드: CI/CD 파이프라인 구축 가이드 (유형: 용어)
파이프라인: Schedule Trigger → Sheets Read → SERP → LLM → Parse JSON
         → Inject Images (2.8s) → Validate Structure → URL/CodeBlock/InternalLinks/Haiku
         → Sheets Update (발행대기)
결과: Exit code 0, finished: true, lastNode: Sheets Update (발행대기)
```

| 지표 | 값 |
|------|---|
| 이미지 삽입 | 2개 (H2 fallback: "기업 환경 적용 사례", "CI/CD 파이프라인 작동 원리") |
| 본문 길이 | 7,651자 (이미지 포함, 이전 4,374자) |
| Unsplash attribution | 2개 (라이선스 준수) |
| 잔류 IMAGE 마커 | 0개 |
| thumbnail_url | 설정됨 (Unsplash small URL) |

#### 테스트 2: 비교 유형 (extractSearchKeyword 적용 후)

```
키워드: Jenkins vs GitHub Actions 비교 (유형: 비교)
1차 시도: Gemini 응답 제어 문자 → Parse JSON 실패 (간헐적 LLM 비결정성)
2차 시도: Exit code 0, finished: true, lastNode: Sheets Update (발행대기)
```

| 지표 | 값 |
|------|---|
| 이미지 삽입 | 1개 (H2 "Jenkins 상세" → 영문 "Jenkins" 추출 → Unsplash 검색 성공) |
| 본문 길이 | 5,217자 |
| H2 헤딩 | 6개 (개요, Jenkins 상세, GitHub Actions 상세, 상세 비교표, 선택 가이드, FAQ) |
| Unsplash attribution | 1개 (라이선스 준수) |
| 잔류 IMAGE 마커 | 0개 |
| thumbnail_url | 설정됨 |

### 테스트 결과

- 단위 테스트: 105건 전체 통과 (기존 95 + 신규 10)
- ruff: 0건 (신규 도입 에러 없음)
- mypy: 0건 (신규 도입 에러 없음, 기존 2건 유지)

---

## Phase 5.8: KEYWORD_BROADENING + 실발행 검증 — ✅ 완료 (2026-03-01)

> **목표**: Unsplash 검색 실패 키워드 해결 + n8n 자격증명 복구 + 전체 파이프라인(A→B) 실발행 검증

### 5.8.1: KEYWORD_BROADENING — Unsplash 검색 실패 해결

**문제**: IT 기술 특화 키워드("Terraform", "Ansible", "SIEM" 등)는 Unsplash에서 검색 결과 0건 반환 → 이미지 삽입 0개

**수정**:
- `KEYWORD_BROADENING` 매핑 테이블 추가 (23개 IT 기술 → Unsplash 검색 친화 키워드)
- `extractSearchKeywords()`: 다중 후보 반환 (원본 → broadening → 제목 영문 → 범용)
- `searchUnsplashWithFallback()`: 키워드 후보 배열 순차 재시도

| 기술 키워드 | 매핑된 Unsplash 키워드 |
|------------|----------------------|
| terraform | cloud infrastructure automation |
| jenkins | software development pipeline |
| kubernetes | cloud container technology |
| ssl/tls | cybersecurity encryption lock |
| siem | cybersecurity monitoring dashboard |
| (총 23개) | ... |

### 5.8.2: n8n 자격증명 복구

**문제**: n8n 볼륨 초기화 후 Google Sheets 자격증명 유실 → REST API body parser 오류로 재등록 불가

**해결**: n8n CLI `import:credentials` 방식으로 우회
1. n8n 암호화 키 확인 (`/home/node/.n8n/config`)
2. `crypto-js` (n8n 내장)로 서비스 계정 자격증명 암호화
3. 워크플로우가 참조하는 credential ID (`amt5R8weAKcq8xmn`)로 import 파일 생성
4. `n8n import:credentials --input=file.json` 실행
5. n8n 재시작 후 Google Sheets API 연결 확인

**n8n 계정 정보**:
- 이메일: `sanghyun6467@gmail.com`
- 워크플로우 ID: `ty52rqOEJ6ZjNF2L`
- 스프레드시트 ID: `1VbyEQNuIAKpmTfk_5pTIjuLb3xlS-kdUfWflmfnFJSA`

### 5.8.3: E2E 테스트 3 — Terraform (KEYWORD_BROADENING 검증)

```
키워드: Terraform이란 무엇인가 (유형: 용어)
결과: 20/20 노드 성공, finished: true
총 실행 시간: ~37초
```

| 지표 | 값 |
|------|---|
| 이미지 삽입 | **4개** (broadening: `cloud infrastructure automation`) |
| 콘텐츠 길이 | 11,177자 |
| H2 헤딩 | 5개 |
| 검증 | 전 항목 True (accurate, logical, complete, useful) |
| Sheets 업데이트 | 발행대기 ✅ |

### 5.8.4: Tistory 실발행 테스트 (Pipeline B)

```bash
MAX_POSTS=1 MIN_DELAY=0 MAX_DELAY=0 python3 -m src.interface.cli
```

**결과**: 발행 성공 — https://kimsanghyeon.tistory.com/197

| 지표 | 값 |
|------|---|
| 키워드 | CI/CD 파이프라인 구축 가이드 (Row 11) |
| 카카오 로그인 | 쿠키 기반 자동 로그인 성공 |
| 본문 주입 | TinyMCE API `setContent()` — 8,992자 |
| 태그 | 7개 (CI/CD, DevOps, Jenkins, GitHub Actions 등) |
| 임시저장 → 공개발행 | 성공 |
| 발행 URL | `/197` |
| 총 소요 시간 | ~47초 |

### 5.8.5: 발행 포스트 품질 검증

| 항목 | 결과 |
|------|------|
| 제목 | CI/CD 파이프라인 구축 완벽 가이드: 초보자를 위한 단계별 실전 튜토리얼 |
| H2 섹션 | 6개 (목차, CI/CD란?, 작동 원리, 적용 사례, 장점과 한계, FAQ) |
| 이미지 | 2개 (Unsplash) |
| 목차(TOC) | 있음 (9개 항목) |
| FAQ | 있음 |
| LD+JSON 스키마 | 2개 |
| 태그 | 7개 |
| 글자수 | 4,376자 |
| 마크다운 잔류물 | 없음 |
| 공개 접근 | 정상 |

**개선 포인트** (향후):
- `loading="lazy"` 속성이 Tistory 에디터에 의해 제거됨 (0/2)
- Unsplash attribution(저작권 표기)이 HTML 변환 시 누락

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `n8n/code_nodes/inject_images.js` | KEYWORD_BROADENING 매핑(23개) + extractSearchKeywords() + searchUnsplashWithFallback() |
| `n8n/workflow_complete.json` | Inject Images 노드 jsCode 업데이트 |

### 의사결정 로그

| 결정 | 근거 |
|------|------|
| KEYWORD_BROADENING 매핑 도입 | "Terraform" 등 IT 기술명은 Unsplash 0건 → 관련 일반 키워드로 확장 |
| 다단계 키워드 fallback (원본→broadening→제목→범용) | 단일 키워드 실패 시에도 최소 `technology software development`로 이미지 확보 |
| n8n CLI `import:credentials` 사용 | REST API body parser 오류 → CLI가 유일한 프로그래밍 가능한 우회 경로 |
| `crypto-js`로 자격증명 암호화 | n8n은 암호화된 data 필드만 import → 현재 인스턴스의 encryptionKey로 암호화 필수 |

---

## Phase 5.9: 발행 품질 강화 (7건) — ✅ 완료 (2026-03-01)

> **목표**: 실발행 포스트(`/197`) 검증에서 발견된 7가지 품질 이슈 수정

### 수정 항목

| # | 우선순위 | 항목 | 수정 파일 | 상태 |
|---|---------|------|----------|------|
| 1 | P0 | 이미지 alt text: Unsplash description → `{keyword} - {section title}` | `inject_images.js` | ✅ |
| 2 | P0 | Lazy loading: 첫 번째 이미지 LCP candidate로 제외 | `tistory_editor.py` | ✅ |
| 3 | P1 | 프롬프트에 코드 예시 작성 지시 추가 | `prompt_a/b/c` | ✅ |
| 4 | P1 | 장점/한계 테이블 분리 작성 지시 추가 | `prompt_a` | ✅ |
| 5 | P1 | Meta description 티스토리 에디터 description 필드 주입 | `tistory_editor.py` | ✅ |
| 6 | P2 | Unsplash attribution: `*...*` → `<small>` 태그 + nofollow 링크 | `inject_images.js` | ✅ |
| 7 | P2 | 외부 링크에 `rel="nofollow noopener" target="_blank"` 자동 추가 | `tistory_editor.py` | ✅ |

### 상세 변경 내역

#### 1. Image alt text (P0)

`searchUnsplashSingle(keyword, sectionTitle)`: 마커 직전 H2 제목 또는 H2 원문 텍스트를 `sectionTitle`로 전달.
alt text 형식: `{검색키워드} - {섹션제목}` (예: `cloud infrastructure automation - Terraform 작동 원리`)

#### 2. Lazy loading LCP (P0)

`_add_lazy_loading()`: regex 치환 콜백에 카운터 도입. 첫 번째 `<img>` 태그는 LCP(Largest Contentful Paint) candidate이므로 `loading="lazy"` 미적용, 두 번째부터 적용.

#### 3. 코드 예시 지시 (P1)

- 프롬프트 A: "설정 파일, CLI 명령어, 스크립트 등 실무 코드 예시를 1개 이상 포함" + 언어 태그 필수
- 프롬프트 B: "각 기술의 설정/사용 예시 코드를 1개 이상 포함" + 언어 태그 필수
- 프롬프트 C: "모든 코드블록에 반드시 언어 태그 부착" (기존 3개 이상 필수 유지)

#### 4. 테이블 분리 (P1)

프롬프트 A: "장점 테이블과 한계 테이블을 **별도로 분리** (각 3행 이상)"

#### 5. Meta description (P1)

`_inject_meta_description(sb, meta_description)`: 발행 전 description 관련 폼 필드(`#post-description`, `textarea[name="description"]` 등) 탐색 후 값 주입.

#### 6. Unsplash credits (P2)

attribution 형식 변경:
- 이전: `*Photo by [Name](url) on [Unsplash](url)*`
- 이후: `<small>Photo by <a href="url" rel="nofollow noopener" target="_blank">Name</a> on <a href="url" rel="nofollow noopener" target="_blank">Unsplash</a></small>`

#### 7. External links nofollow (P2)

`_add_nofollow_to_external_links(html_text, blog_name)`: HTML 내 모든 `<a>` 태그 검사. 내부 링크(`{blog_name}.tistory.com`), 앵커 링크(`#`), 이미 `rel=` 있는 태그는 건드리지 않고, 나머지 외부 링크에 `rel="nofollow noopener" target="_blank"` 추가.

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `n8n/code_nodes/inject_images.js` | alt text 형식 변경, attribution `<small>` + nofollow, `searchUnsplashSingle/WithFallback`에 sectionTitle 파라미터 추가, `findPrecedingH2()` 헬퍼 |
| `n8n/prompts/prompt_a_terminology.md` | 코드 예시 지시 + 테이블 분리 지시 + 체크리스트 항목 추가 |
| `n8n/prompts/prompt_b_comparison.md` | 코드 예시 지시 + 체크리스트 항목 추가 |
| `n8n/prompts/prompt_c_troubleshooting.md` | 코드블록 언어 태그 필수 지시 추가 |
| `n8n/workflow_complete.json` | inject_images.js 변경 동기화 |
| `src/infrastructure/browser/tistory_editor.py` | `_add_lazy_loading()` LCP 제외, `_add_nofollow_to_external_links()` 신규, `_inject_meta_description()` 신규 |
| `tests/unit/infrastructure/test_markdown_to_html.py` | lazy loading 테스트 수정 + nofollow 테스트 5건 추가 (총 111건) |

### 테스트 결과

- 단위 테스트: **111건 전체 통과** (기존 105 → 신규 6건 추가)
- ruff: 0건 (기존 1건 pre-existing — post_content.py E501)
- workflow import: n8n 컨테이너 반영 완료

---

## Phase 5.10: 버그 수정 세션 (3건) — ✅ 완료 (2026-03-02)

> **배경**: Phase 5.9 완료 후 발견된 3가지 버그 수정. 통합 테스트 2건 실패, Row 12 발행실패, n8n 모니터링 미작동.

### Bug 1 (P0): 카카오 로그인 셀렉터 오류

**문제**: `#loginId--1`, `#password--2`는 React가 생성하는 불안정 ID. 카카오 페이지 업데이트 시 변경됨 → 통합 테스트 2건 실패

**수정**: `kakao_auth.py` — Fallback Chain + JS 구조 기반 탐색

| 추가 항목 | 내용 |
|----------|------|
| `KAKAO_LOGIN_ID_SELECTORS` | `#loginId--1` → `input[name='loginId']` → `input[type='email']` → `input[id^='loginId']` |
| `KAKAO_PASSWORD_SELECTORS` | `#password--2` → `input[name='password']` → `input[type='password']` → `input[id^='password']` |
| `KAKAO_SUBMIT_SELECTORS` | `button.submit` → `button[type='submit']` |
| `_find_kakao_element()` | `dom_selectors.find_element()`와 동일 패턴의 헬퍼 |
| `_find_kakao_elements_by_js()` | 최종 fallback — 페이지의 모든 input을 순회하여 email→password→submit 구조 기반 탐색 |

**기존 동작 보존**: 원래 셀렉터(`#loginId--1` 등)를 chain 최상위에 유지 → 작동 시 기존과 동일

**실전 검증**: Row 12 재발행 시 `#loginId--1` visible 실패 → JS fallback으로 자동 전환되어 로그인 성공

### Bug 2 (P1): Row 12 발행 실패 재시도

**문제**: Row 12 "Jenkins vs GitHub Actions 비교" — 이전 UI 버튼 코드에서 실패. DDD 상태 머신에 FAILED→PENDING 전이 없어 재시도 불가

**수정**: 4-Layer 전체에 걸친 변경

| 레이어 | 파일 | 변경 |
|--------|------|------|
| Domain | `post.py` | `reset_failed_to_pending()` 메서드 추가 (FAILED→PENDING, error_message 초기화) |
| Domain | `post_repository.py` | `find_failed()` 추상 메서드 추가 |
| Infrastructure | `google_sheets_repo.py` | `find_failed()` 구현 (STATUS_FAILED 필터링) |
| Infrastructure | `in_memory_repo.py` | `find_failed()` 구현 (테스트용) |
| Application | `reset_stuck_posts.py` | `retry_failed: bool = False` 파라미터 + 실패 재시도 로직 (옵트인) |
| Interface | `cli.py` | `RETRY_FAILED` 환경변수 읽기 → UseCase 전달 |
| Script | `scripts/reset_row12.py` | Row 12 즉시 리셋 (1회성 gspread 스크립트) |

**테스트 추가** (5건):
- `test_post_entity.py`: `TestResetFailedToPending` — 정상 전이, 비-FAILED 에러, error_message 클리어
- `test_reset_stuck_usecase.py`: `TestRetryFailed` — 옵트인 동작, 기본 비활성

**Row 12 재발행 결과**:
- `python3 scripts/reset_row12.py` → 발행실패 → 발행대기 리셋 완료
- `RETRY_FAILED=true MAX_POSTS=1 python3 -m src.interface.cli` → 발행 성공
- 발행 URL: https://kimsanghyeon.tistory.com/207
- 본문: 9,530자 TinyMCE 주입, 태그 5개

### Bug 3 (P2): n8n API 키 누락

**문제**: `/tmp/n8n_api_key.txt` 미존재 → `check_status.sh`, `check_last_run.sh` 모니터링 미작동

**수정**:

| 파일 | 변경 |
|------|------|
| `setup_n8n_apikey.sh` (신규) | n8n Docker에서 API 키 생성 + `/tmp/n8n_api_key.txt` 저장 + 검증 |
| `check_status.sh` | API 키 로드 fallback chain (파일 → `.env` → 환경변수) |
| `check_last_run.sh` | 동일 fallback chain 적용, 에러 메시지에 해결 안내 추가 |
| `.env.example` | `N8N_API_KEY=` 항목 추가 |

### 커밋 내역

| 커밋 | 메시지 |
|------|--------|
| `cb7ba25` | `fix(infra): replace hardcoded Kakao login selectors with fallback chain` |
| `08063b7` | `fix(domain): add FAILED→PENDING transition for post retry recovery` |
| `8fef5be` | `fix(ops): add n8n API key setup script and .env fallback for monitoring` |
| `4b7087e` | `fix(infra): tistory editor 발행 안정화 및 셀렉터 보강` |

### 검증 결과

| 항목 | 결과 |
|------|------|
| 단위 테스트 | **116 passed** (기존 111 + 신규 5) |
| 통합 테스트 | **9 passed** (이전 2 failed → 0 failed) |
| ruff | 0 errors |
| mypy (kakao_auth.py) | 0 errors |
| Row 12 재발행 | 성공 (https://kimsanghyeon.tistory.com/207) |

### 수정 파일 요약 (13개)

| 파일 | 변경 유형 |
|------|----------|
| `src/infrastructure/browser/kakao_auth.py` | 셀렉터 fallback chain 상수 + 헬퍼 2개 + `_enter_credentials_and_wait` 재작성 |
| `src/domain/entities/post.py` | `reset_failed_to_pending()` 메서드 추가 |
| `src/domain/ports/post_repository.py` | `find_failed()` 추상 메서드 추가 |
| `src/infrastructure/persistence/google_sheets_repo.py` | `find_failed()` 구현 + `STATUS_FAILED` import |
| `src/infrastructure/persistence/in_memory_repo.py` | `find_failed()` 구현 |
| `src/application/use_cases/reset_stuck_posts.py` | `retry_failed` 옵트인 파라미터 + 실패 재시도 로직 |
| `src/interface/cli.py` | `RETRY_FAILED` 환경변수 읽기 |
| `scripts/reset_row12.py` | 1회성 Row 12 리셋 스크립트 (신규) |
| `setup_n8n_apikey.sh` | n8n API 키 자동 생성+저장 스크립트 (신규) |
| `check_status.sh` | API 키 로드 fallback chain 적용 |
| `check_last_run.sh` | 동일 fallback chain 적용 |
| `.env.example` | `N8N_API_KEY=` 추가 |
| `tests/unit/domain/test_post_entity.py` | `TestResetFailedToPending` 3건 추가 |
| `tests/unit/application/test_reset_stuck_usecase.py` | `TestRetryFailed` 2건 추가 |

---

## Phase 5.11: Mermaid 다이어그램 이미지 대체 — ✅ 완료 (2026-03-02)

> **배경**: Unsplash 스톡 사진이 IT 블로그 본문 내용과 연관성이 낮은 문제. `<!-- IMAGE: -->` 마커 기반 Unsplash 다중 삽입을 **LLM 생성 Mermaid 다이어그램**으로 대체.

### 핵심 변경

| 구분 | 기존 | 변경 |
|------|------|------|
| 본문 이미지 | Unsplash 스톡 사진 (H2당 1장, 최대 4장) | Mermaid 다이어그램 → kroki.io SVG (LLM이 직접 생성) |
| 이미지 마커 | `<!-- IMAGE: {keyword} -->` | ` ```mermaid ` 코드블록 (최소 2개) |
| 렌더링 | Unsplash API 검색 + URL 삽입 | kroki.io POST → SVG → base64 `<img>` 태그 |
| 썸네일 | Unsplash 첫 번째 이미지 | Unsplash 1장 유지 (OG 이미지용) |
| 실패 처리 | 마커 제거 | 원본 코드블록 유지 (graceful degradation) |

### 수정 파일 (8개)

| 파일 | 변경 내용 |
|------|----------|
| `n8n/prompts/prompt_a_terminology.md` | 규칙 5: IMAGE 마커 → mermaid 코드블록 지시, 체크리스트 업데이트 |
| `n8n/prompts/prompt_b_comparison.md` | 동일 패턴 적용 |
| `n8n/prompts/prompt_c_troubleshooting.md` | 동일 패턴 적용 |
| `n8n/code_nodes/inject_images.js` | 대폭 재작성: Mermaid→kroki.io SVG + Unsplash 썸네일만 유지 (272줄→175줄) |
| `n8n/code_nodes/validate_structure.js` | #9 추가: Mermaid 잔류 감지 (warning only) |
| `src/infrastructure/browser/tistory_editor.py` | `_preserve_mermaid_blocks()` + `_style_mermaid_fallback()` + `validate_html()` 경고 추가 |
| `tests/unit/infrastructure/test_markdown_to_html.py` | 5건 추가: TestMermaidFallback (3) + TestValidateHtmlMermaid (2) |
| `n8n/workflow_complete.json` | Inject Images, Validate Structure 노드 jsCode 동기화 |

### inject_images.js 주요 로직

1. **Mermaid 블록 추출**: ` ```mermaid ... ``` ` 정규식 매칭
2. **kroki.io 렌더링**: `POST https://kroki.io/mermaid/svg` (Content-Type: text/plain)
3. **SVG → `<img>`**: `data:image/svg+xml;base64,...` 인라인 삽입
4. **역순 치환**: 인덱스 밀림 방지
5. **thumbnail_url**: Unsplash 제목 기반 1장 검색 (OG 이미지용)

### tistory_editor.py 적응 사항

플랜에서 `fenced_code` extension이 `class="language-mermaid"`를 생성한다고 가정했으나, `codehilite` extension이 선처리하여 구문 강조 코드로 변환됨.

**해결**: `_preserve_mermaid_blocks()`를 markdown 변환 전 사전 처리로 추가. 잔류 mermaid 블록을 styled HTML(`<div class="mermaid-fallback">`)로 직접 변환하여 codehilite 간섭을 회피.

### 커밋 내역

| 커밋 | 메시지 |
|------|--------|
| `3e3d526` | `feat(n8n): replace Unsplash stock photos with Mermaid diagrams via kroki.io` |

### 검증 결과

| 항목 | 결과 |
|------|------|
| 단위 테스트 | **121 passed** (기존 116 + 신규 5) |
| ruff | 0 errors |
| mypy | 0 new errors (기존 13건 — markdown stubs, Any return) |

---

## Phase 5.12: 수동 검증 + Sheets 50K/JSON fence 수정 — ✅ 완료 (2026-03-02)

> **배경**: Phase 5.11 수동 검증 과정에서 3가지 치명적 문제 발견 및 해결.

### 발견 및 해결한 문제 (3건)

| # | 문제 | 원인 | 해결 |
|---|------|------|------|
| 1 | Gemini JSON 응답 5K자에서 잘림 (61K 공백 패딩) | JSON content 안의 ` ```mermaid ` 백틱이 Gemini 응답 생성을 혼란시킴 | `[MERMAID]...[/MERMAID]` 커스텀 마커로 대체 — 백틱 충돌 제거 |
| 2 | Parse JSON Response fence 탐지 오류 | `lastIndexOf('` ``` `')` 가 mermaid 코드블록의 닫는 백틱을 JSON 끝으로 오인 | 커스텀 마커 도입으로 ` ``` ` 간섭 원천 제거 |
| 3 | Google Sheets 50K 셀 제한 초과 | base64 SVG (~10K/개) 및 인라인 SVG (~10K/개) 모두 50K 초과 | zlib deflate + base64url → kroki.io GET URL (~200자/개) |

### 검증 과정 (n8n 수동 실행 6회)

| 실행 | 결과 | 문제 | 조치 |
|------|------|------|------|
| ID 6 | ✅ 성공 | Gemini가 mermaid 미생성 | Route Prompt 노드 프롬프트가 하드코딩 — mermaid 지시 추가 |
| ID 7 | ❌ 실패 | Sheets 50K 초과 (base64 SVG) | base64 → 인라인 SVG로 변경 |
| ID 8 | ❌ 실패 | Sheets 50K 초과 (인라인 SVG) | kroki.io GET URL 방식으로 전면 변경 |
| ID 10 | ❌ 실패 | Parse JSON fence 탐지 오류 + Gemini 잘림 | `[MERMAID]` 커스텀 마커 도입 |
| ID 11 | ✅ 성공 | — | 최종 구조 확정 |

### 최종 아키텍처

```
LLM (Gemini) → content에 [MERMAID]graph TD...[/MERMAID] 마커 생성
  ↓
inject_images.js → [MERMAID] 추출 → zlib.deflateSync + base64url
  → <img src="https://kroki.io/mermaid/svg/{encoded}"> (~200자)
  ↓
Google Sheets 저장 (5171자 — 50K 제한 안전)
  ↓
tistory_editor.py → 잔류 [MERMAID] 있으면 kroki.io POST로 SVG 렌더링
```

### 수정 파일 (8개)

| 파일 | 변경 내용 |
|------|----------|
| `docker-compose.yml` | `NODE_FUNCTION_ALLOW_BUILTIN=zlib` 환경변수 추가 |
| `n8n/code_nodes/inject_images.js` | SVG 임베딩 → `zlib.deflateSync` + kroki.io GET URL, 마커 `[MERMAID]` 패턴 |
| `n8n/code_nodes/validate_structure.js` | 잔류 탐지: ` ```mermaid ` → `[MERMAID]` 패턴 |
| `n8n/prompts/prompt_a_terminology.md` | ` ```mermaid ` → `[MERMAID]...[/MERMAID]` 지시 |
| `n8n/prompts/prompt_b_comparison.md` | 동일 |
| `n8n/prompts/prompt_c_troubleshooting.md` | 동일 |
| `n8n/workflow_complete.json` | Route Prompt / Inject Images / Validate Structure 3개 노드 동기화 |
| `src/infrastructure/browser/tistory_editor.py` | `_render_mermaid_via_kroki()` 추가, `_preserve_mermaid_blocks()` 양 패턴 지원 |

### 주요 발견: Route Prompt 하드코딩

프롬프트 `.md` 파일은 n8n 워크플로우에서 직접 사용되지 않음. Route Prompt (A/B/C) 노드의 `jsCode`에 프롬프트가 하드코딩되어 있어, `.md` 파일 수정만으로는 반영 불가. `workflow_complete.json` 내 jsCode를 직접 수정해야 함.

### 커밋 내역

| 커밋 | 메시지 |
|------|--------|
| `fcf6552` | `fix(n8n): resolve Sheets 50K limit and JSON fence collision for Mermaid diagrams` |

### 검증 결과

| 항목 | 결과 |
|------|------|
| n8n 실행 ID 11 | ✅ 전 노드 성공 (Sheets Update 발행대기 포함) |
| Gemini 응답 | `[MERMAID]` 2개 생성, 7060자, finishReason=STOP (공백 패딩 없음) |
| Inject Images | 2개 발견 → 2개 kroki.io URL 변환 성공, 실패 0 |
| Content 크기 | 5171자 (50K 제한 안전) |
| kroki.io URL | SVG 정상 반환 확인 (curl 테스트) |
| 단위 테스트 | **121 passed** |
| ruff | 0 errors |

---

## Phase 5.13: 발행 후 HTTP 검증 + 비공개 자동 복구 — ✅ 완료 (2026-03-02)

### 발견된 문제

Pipeline B로 발행한 게시글 `/210`, `/211`이 **403 (비공개)** 반환.

**조사 결과:**
- RSS/Sitemap에 /206까지만 노출, /210~211 미포함
- HTTP 403 = "권한이 없거나 존재하지 않는 페이지" = 비공개 상태
- `_select_public_mode()`가 공개 라디오 버튼을 클릭하지만, 실패 시 **경고만 출력하고 계속 진행** → 비공개 상태로 발행

### 해결 방안

**1) 발행 후 공개 상태 검증 (자동)**

`publish_post()` 흐름에 검증 단계 추가:
```
발행 → URL 획득 → HTTP HEAD 검증 → 403 감지 시 → visibility=20 수정 API → 재검증
```

**2) 비공개 게시글 수동 복구**

Tistory 관리자 페이지에서 210, 211번 글을 수동으로 공개 전환 → **HTTP 200 확인**.

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/infrastructure/browser/tistory_editor.py` | `_verify_published_url()`, `_extract_post_id()`, `_fix_post_visibility()` 추가 + `publish_post()` 검증 흐름 통합 |
| `tests/unit/infrastructure/test_markdown_to_html.py` | `TestExtractPostId` (4건) + `TestVerifyPublishedUrl` (2건) 추가 |

### 검증 결과

| 항목 | 결과 |
|------|------|
| `/210` HTTP | 403 → **200 (공개)** |
| `/211` HTTP | 403 → **200 (공개)** |
| 단위 테스트 | **127 passed** (기존 121 + 신규 6) |
| ruff | 0 errors |
| 커밋 | `57f20ce` — `fix(infra): add post-publish HTTP verification and auto-visibility recovery` |

---

## Phase 5.14: 일일 발행 제한 감지 + 대량 발행 — ✅ 완료 (2026-03-02)

### Pipeline A — 15건 콘텐츠 일괄 생성

n8n Pipeline A 수동 실행으로 "대기" 상태 15건 키워드를 전량 처리.

| 항목 | 결과 |
|------|------|
| 입력 키워드 | 15건 (rows 33-47) |
| 출력 상태 | **발행대기 15건** (검수필요 0건 — 100% 통과) |
| 처리 시간 | ~90초 |

### Pipeline B — 3건 발행 + 일일 제한 발견

headed 모드로 Pipeline B 실행, 3건 발행 후 Tistory 일일 제한 도달.

| # | 키워드 | URL | HTTP |
|---|--------|-----|------|
| 1 | API Gateway란 무엇인가 | /212 | **200** |
| 2 | 컨테이너 오케스트레이션이란 | /213 | **200** |
| 3 | OAuth 2.0 인증 플로우 가이드 | /214 | **200** |
| 4 | Elasticsearch 검색엔진 구축 가이드 | — | **403 "최대 15개까지"** |

**일일 제한**: "하루에 새롭게 공개 발행할 수 있는 글은 최대 15개까지입니다." (Tistory 정책)

### 코드 개선 — 일일 발행 제한 감지

기존: 일일 제한 시 포스트가 "발행실패"로 마킹됨 → 수동 리셋 필요.
개선: `DailyPublishLimitError` 예외로 배치 즉시 중단 + 해당 포스트 "발행대기" 복원.

| 파일 | 변경 내용 |
|------|----------|
| `src/domain/exceptions.py` | `DailyPublishLimitError` 예외 클래스 추가 |
| `src/infrastructure/browser/tistory_editor.py` | React alert / API 403 응답에서 "최대 15개까지" 패턴 감지 → 예외 발생 |
| `src/application/use_cases/publish_posts.py` | `DailyPublishLimitError` 캐치 → 배치 중단, 현재 포스트 `reset_to_pending()` |
| `tests/unit/application/test_publish_posts_usecase.py` | `TestPublishPostsDailyLimit` (2건) 추가 |

### 검증 결과

| 항목 | 결과 |
|------|------|
| 신규 발행 | 3건 (/212, /213, /214 — 모두 HTTP 200) |
| 발행대기 잔여 | 12건 (내일 09:00 AM cron 자동 발행) |
| 단위 테스트 | **129 passed** (기존 127 + 신규 2) |
| ruff | 0 errors |
| 커밋 | `db327bf` — `fix(infra): detect Tistory daily publish limit and stop batch gracefully` |

---

## Phase 6: 콘텐츠 누적 + SEO 최적화 — 🔲 미시작

> **기간**: W3~6 (2026-03-15 ~ 2026-04-11)
> **목표**: 20건 누적 + 검증 통과율 85%+ + 내부 링크 구조 완성

| # | 항목 | 상태 | 게이트 |
|---|------|------|--------|
| 6.1 | 주 3~5건 안정 발행 확인 | 🔲 | 자동 발행률 80%+ |
| 6.2 | 프롬프트 튜닝 (검수필요 비율 > 20% 시) | 🔲 | 통과율 85%+ |
| 6.3 | 내부 링크 구조 강화 (허브-스포크) | 🔲 | 글당 내부링크 3~5개 |
| 6.4 | FAQ 리치 스니펫 색인 확인 | 🔲 | FAQ 색인 1건+ |
| 6.5 | 총 20건 발행 달성 | 🔲 | W4: 15건, W6: 20건 |
| 6.6 | 제목/메타 A/B 테스트 (CTR 저조 글) | 🔲 | CTR 개선 확인 |
| 6.7 | 반응형 스킨 + Core Web Vitals 점검 | 🔲 | LCP < 2.5s |
| 6.8 | 카테고리 정비 (3~5개 균등 배분) | 🔲 | 카테고리당 4건+ |

### 주간 KPI 기록 템플릿

| 주차 | 발행수 | 색인수 | 총 노출 | 평균 CTR | 일 유입 | 검증통과율 | 비고 |
|------|--------|--------|---------|----------|---------|-----------|------|
| W1 | | | | | | | |
| W2 | | | | | | | |
| W3 | | | | | | | |
| W4 | | | | | | | |
| W5 | | | | | | | |
| W6 | | | | | | | |

---

## Phase 7: 성장 + 수익화 — 🔄 진행 중 (2026-03-05~)

> **목표**: 잔여 발행 완료 → 색인 확인 → 애드센스 승인 → 일 유입 20명

### 즉시 실행 (2026-03-05)

| # | 항목 | 상태 | 비고 |
|---|------|------|------|
| 7.0a | 잔여 발행대기 포스트 일괄 발행 | ✅ 완료 | /220~/225 (7건 발행, 에디터 리로드 수정 포함) |
| 7.0b | Tistory sitemap.xml 확인 | ✅ 완료 | 498 URL, /220~/225 포함 확인. GSC 수동 제출 필요 |
| 7.0c | 기 발행 39건 중 색인 현황 확인 | 🔲 | GSC URL 검사 |

### 중기 목표

| # | 항목 | 상태 | Go/No-Go |
|---|------|------|----------|
| 7.1 | 노출 500+ / 색인 10+ | 🔲 | **미달 → 피벗 레벨 1** |
| 7.2 | 애드센스 승인 신청 | 🔲 | 필수 페이지 + 20건+ 글 |
| 7.3 | 광고 배치 최적화 (수동 3~4개) | 🔲 | H2 위/중간/결론 앞/사이드바 |
| 7.4 | 고CPC 키워드 집중 (에러 해결 글 확대) | 🔲 | CPC > 1,000원 |
| 7.5 | 일 유입 20명 | 🔲 | **미달 → 피벗 레벨 2~3** |
| 7.6 | CPA 제휴 검토 (리더스CPA/애드팟) | 🔲 | 수익 다각화 |
| 7.7 | 워드프레스 전환 검토 (피벗 시) | 🔲 | 커스텀 도메인 + WP |

### 피벗 판단 기준 (재확인)

| 레벨 | 트리거 | 액션 |
|------|--------|------|
| 1 | W8 색인 10건 미달 | 키워드 하향, 롱테일 집중, 제목/메타 교체 |
| 2 | W10 CTR 1% 미달 | Matplotlib 차트 삽입, 원본 데이터 공개 |
| 3 | W12 일 유입 10명 미달 | 워드프레스 전환 (REST API, 301 리다이렉트) |

---

## Phase 6: 콘텐츠 누적 + SEO 최적화 — ✅ 완료 (2026-03-03~03-05)

### 목표
내부 링크 자동 삽입 + CWV 최적화 + 카테고리 자동 지정으로 SEO 경쟁력 확보

### 완료된 작업

| # | 항목 | 상태 | 비고 |
|---|------|------|------|
| 6.1 | PostContent에 internal_link_keywords 필드 추가 | ✅ 완료 | JSON 파싱 + 쉼표 fallback |
| 6.2 | GoogleSheetsRepo에서 Column S(internal_links) 읽기 | ✅ 완료 | |
| 6.3 | 내부 링크 자동 삽입 모듈 (internal_linker.py) | ✅ 완료 | 최대 5개, h1~h3/a/code/pre 제외 |
| 6.4 | PublishPostsUseCase에 내부 링크 주입 연결 | ✅ 완료 | _attach_internal_link_map() |
| 6.5 | 카테고리 자동 지정 (CATEGORY_MAP + API 전달) | ✅ 완료 | 실제 Tistory ID 매핑 (용어→991463, 비교/에러→966384) |
| 6.6 | CWV 최적화: fetchpriority="high" + dns-prefetch | ✅ 완료 | 첫 이미지 LCP candidate 처리 |
| 6.7 | Mermaid 이미지에 width="800" 추가 (CLS 방지) | ✅ 완료 | inject_images.js |
| 6.8 | 내부 링크 단위 테스트 11건 | ✅ 완료 | test_internal_linker.py |
| 6.9 | 허브-스포크 내부 링크 서비스 도입 | ✅ 완료 | InternalLinkService — 키워드 겹침 기반 허브 식별 + 우선순위 링크 선정 |
| 6.10 | Post 엔티티에 internal_link_keywords 필드 추가 | ✅ 완료 | `dataclass(field)` + GoogleSheetsRepo JSON 파싱 |
| 6.11 | 로그 시스템 정상화 | ✅ 완료 | 기본 경로 `/var/log` → `logs/`, cli.py에서 PROJECT_ROOT 기준 절대 경로 전달 |
| 6.12 | run_pipeline_b.sh PROJECT_DIR 경로 수정 | ✅ 완료 | `claudeagent/` → `Core Web Vitals/` |
| 6.13 | 허브-스포크 + 내부 링크 단위 테스트 | ✅ 완료 | test_internal_link_service.py 18건 + test_post_entity.py 2건 추가 |

### Phase 6 실발행 검증 (2026-03-04~05)

5건 발행 검증 (215~219):

| 포스트 | URL | 공개 | 내부링크 | 카테고리 | 태그 |
|--------|-----|------|----------|----------|------|
| Elasticsearch 검색엔진 구축 가이드 | /215 | ✅ | - | - (API 이전) | ✅ |
| IaC(Infrastructure as Code)란 | /216 | ✅ | - | - (ID 오류) | ✅ 8개 |
| 네트워크 세그멘테이션이란 | /217 | ✅ | - | - (ID 오류) | ✅ |
| Terraform vs Pulumi 비교 | /218 | ✅ | ✅ +51자 | ❌ (ID=0) | ✅ 5개 |
| Datadog vs New Relic 비교 | /219 | ✅ | - (관련 없음) | ✅ 배운것 | ✅ 7개 |

**해결된 이슈:**
1. **Chrome user_data_dir 실행 실패** → `chromium_arg` 방식으로 전환
2. **비공개 발행 (403)** → React fiber onChange 핸들러 직접 호출 + XHR API 우선
3. **내부 링크 미삽입** → 양방향 부분 문자열 매칭 + published 키워드 직접 검색 전략
4. **카테고리 미적용 (ID 불일치)** → category.json API로 실제 ID 확인, CATEGORY_MAP 갱신
5. **entryId null** → URL 경로에서 ID 추출
6. **CWV 429 rate limit** → API 호출 간 3초 딜레이 + 429시 10초 추가 대기

### 주간 KPI (W1: 2026-03-03~05)

| 지표 | 목표 | 실측 |
|------|------|------|
| 발행 글 수 | 50건 | 39건 (5건 Phase 6에서 추가) |
| 단위 테스트 | 130+ | 201건 |
| ruff | 0 errors | 0 errors |
| 공개 발행 | 100% | ✅ 100% (React fiber + visibility=20) |
| 내부 링크 | 글당 0~5개 | ✅ 본문에 관련 키워드 있을 때만 삽입 |
| 카테고리 지정 | 100% | ✅ 용어→991463, 비교/에러→966384 |

---

## 의사결정 로그

| 일자 | 결정 사항 | 근거 |
|------|----------|------|
| 2026-02-28 | `_is_tistory_logged_in()` hostname 기반 판별로 변경 | OAuth redirect URL query param에서 false positive 발생 |
| 2026-02-28 | 카카오 버튼 클릭 후 URL 안정화 폴링 (최대 15초) | 고정 sleep 3초로는 2FA 리다이렉트 완료 보장 불가 |
| 2026-02-28 | `cli.py`에 `user_data_dir=".browser_data"` 추가 | 쿠키 영속화로 2FA 반복 방지, test_login.py와 동작 일치 |
| 2026-02-28 | Pipeline B 발행 버그 3건 발견 (B1: 공개발행 미구현, B2: 본문 미입력, B3: 태그 미입력) | Phase 5 수동 검증 중 육안 확인 |
| 2026-02-28 | `window.confirm` 오버라이드 방식 채택 | 마크다운 전환 팝업이 네이티브 `window.confirm()`이라 DOM 셀렉터/alert 핸들러 불가 → JS 오버라이드가 유일한 방법 |
| 2026-02-28 | 임시저장→공개발행 2단계 전략 채택 | 본문 주입 후 바로 발행하면 내용 미반영 가능성 → 임시저장으로 서버 저장 먼저, 그 후 공개 전환 |
| 2026-02-28 | Haiku→Sonnet 4.5 모델 변경 (Phase 5.5) | Haiku 생성 본문 495~1,282자로 목표 미달 — Sonnet 4.5 + 8192 토큰으로 품질 확보 |
| 2026-02-28 | "2000자 이내" → "최소 N자 이상" (Phase 5.5) | 상한 지시가 모델의 짧은 출력을 유도하는 근본 원인 |
| 2026-02-28 | SERP 구조화 파싱 노드 추가 (Phase 5.5) | organic 5개만 → organic 7 + PAA 5 + related 8 + KG 활용 |
| 2026-02-28 | 검증 4항목 확장 (Phase 5.5) | 정확성+논리만으로는 짧고 피상적 콘텐츠가 통과 |
| 2026-02-28 | 본문 길이 최소 검증 추가 (Phase 5.5) | 495자 본문도 검증 통과하는 문제 해결 |
| 2026-02-28 | LLM Provider 추상화 — Code Node 기반 (Phase 5.6) | `.env` 한 줄로 Gemini↔Claude 전환, 워크플로우 JSON 수정 0건 |
| 2026-02-28 | Lenient 재귀 하강 JSON 파서 도입 (Phase 5.6) | Gemini가 생성하는 JSON의 이스케이프 안 된 `"`, 제어 문자, 유효하지 않은 이스케이프를 자동 복구 |
| 2026-02-28 | Haiku검증 컬럼에 `.verification` 서브객체만 저장 (Phase 5.6) | Google Sheets 셀 50K 문자 제한 초과 방지 |
| 2026-02-28 | Gemini을 기본 LLM provider로 설정 (Phase 5.6) | 비용 효율 (무료 tier) + API 키 단순화 |
| 2026-02-28 | 프롬프트에 tags 필드 추가 + Sheets 매핑 보완 (Phase 5) | 품질 검수에서 태그 누락 14건 발견 → 자동 생성으로 전환 |
| 2026-02-28 | 보류 10건 → 대기 전환 (Phase 5) | 01:00 AM 자동 실행 검증을 위해 Pipeline A 입력 데이터 확보 |
| 2026-02-28 | check_status.sh / check_last_run.sh 모니터링 도구 도입 (Phase 5) | Docker/n8n/Sheets 상태를 한눈에 파악, 아침 점검 자동화 |
| 2026-02-28 | Pipeline B 비공개→공개 발행으로 변경 (Phase 5) | `_select_private_mode()`→`_select_public_mode()` + `visibility=0`, SEO 색인 불가 해소 |
| 2026-02-28 | SD-WAN 공개 발행 테스트 성공 (Phase 5) | RSS 피드에 정상 노출 확인 (https://kimsanghyeon.tistory.com/182) |
| 2026-03-01 | MD→HTML 변환 버그 수정 — 방향 A 채택 (Phase 5) | 마크다운 모드 + CodeMirror setValue()는 서버에 raw MD 저장 → Python `markdown` 라이브러리로 HTML 변환 후 WYSIWYG 모드(TinyMCE)에 주입 |
| 2026-03-01 | `markdown>=3.5` 패키지 추가 + extensions: tables, fenced_code, nl2br, sane_lists | 테이블/코드블록/줄바꿈/목록 정상 변환 보장 |
| 2026-03-01 | HTML 검증 함수 `validate_html()` 도입 | `<h2>/<h3>`, `<p>` 존재 + 잔여 MD 문법(`## `, `**`, `\|---\|`) 미포함 검사 |
| 2026-03-01 | KEYWORD_BROADENING 매핑 테이블 도입 (Phase 5.8) | "Terraform" 등 IT 기술 키워드가 Unsplash 검색 0건 → 23개 기술별 일반 키워드 매핑 |
| 2026-03-01 | 다단계 키워드 fallback 전략 (Phase 5.8) | 원본 → broadening → 제목 영문 → 범용, 순차 재시도로 이미지 확보율 극대화 |
| 2026-03-01 | n8n CLI `import:credentials` 방식 채택 (Phase 5.8) | REST API body parser 오류로 POST 불가 → CLI + crypto-js 암호화로 자격증명 프로그래밍 등록 |
| 2026-03-01 | Tistory 실발행 검증 완료 (Phase 5.8) | Pipeline A(n8n) → Pipeline B(Selenium) 전체 흐름 실증, /197 공개 발행 확인 |
| 2026-03-01 | Image alt text를 `{keyword} - {section title}` 형식으로 변경 (Phase 5.9) | Unsplash alt_description은 영문이고 맥락 부족 → 검색키워드+섹션제목 조합이 SEO에 유리 |
| 2026-03-01 | 첫 번째 이미지 lazy loading 제외 (Phase 5.9) | 첫 이미지가 LCP(Largest Contentful Paint) candidate → lazy loading 시 Core Web Vitals 점수 하락 |
| 2026-03-01 | Unsplash attribution을 `<small>` + nofollow로 변경 (Phase 5.9) | 저작권 표기는 필수이나 외부 링크 juice 유출 방지 + 시각적으로 본문과 구분 |
| 2026-03-01 | 외부 링크에 nofollow/noopener/target="_blank" 자동 추가 (Phase 5.9) | SEO link juice 유출 방지 + 보안(noopener) + UX(새 탭 열기) |
| 2026-03-01 | 프롬프트에 코드 예시 + 테이블 분리 지시 추가 (Phase 5.9) | 실발행 검증에서 코드블록 0개, 장점/한계가 하나의 테이블로 구분이 어려운 문제 발견 |
| 2026-03-02 | 카카오 로그인 셀렉터 Fallback Chain 도입 (Phase 5.10) | React 생성 ID(`#loginId--1`)가 불안정 → name/type/id-prefix + JS 구조 탐색으로 3단계 fallback |
| 2026-03-02 | FAILED→PENDING 전이를 옵트인(`RETRY_FAILED=true`)으로 설계 (Phase 5.10) | 실패 원인 미해결 상태에서 자동 재시도는 위험 → 명시적 옵트인으로 의도적 재시도만 허용 |
| 2026-03-02 | n8n API 키 로드 fallback chain 도입 (Phase 5.10) | 파일(/tmp) 단일 소스 → 파일/.env/환경변수 3단계로 유연성 확보, setup 스크립트로 초기 설정 자동화 |
| 2026-03-02 | Unsplash 스톡 사진 → Mermaid 다이어그램 대체 (Phase 5.11) | 스톡 사진이 IT 블로그 본문과 연관성 낮음 — LLM이 직접 생성한 기술 다이어그램이 콘텐츠 가치 높음 |
| 2026-03-02 | kroki.io POST API 단일 방식 채택 (Phase 5.11) | GET(deflate+base64url) 대비 구현 단순, n8n httpRequest 호환성 우수, 실패 시 원본 유지로 안전 |
| 2026-03-02 | codehilite 간섭 회피를 위한 Mermaid 사전 처리 (Phase 5.11) | codehilite가 mermaid 블록을 구문 강조 처리하여 language-mermaid 클래스 소실 → markdown 변환 전 HTML로 사전 변환 |
| 2026-03-02 | `[MERMAID]...[/MERMAID]` 커스텀 마커 도입 (Phase 5.12) | JSON content 안의 ` ``` ` 백틱이 (1) Gemini 응답 truncation (2) Parse JSON fence 탐지 오류를 유발 → 백틱 없는 커스텀 마커로 근본 해결 |
| 2026-03-02 | kroki.io GET URL 방식 전환 (Phase 5.12) | 인라인 SVG/base64 모두 Google Sheets 50K 셀 제한 초과 → zlib deflate + base64url로 ~200자 URL 생성, 브라우저가 on-demand 렌더링 |
| 2026-03-02 | `NODE_FUNCTION_ALLOW_BUILTIN=zlib` Docker 환경변수 추가 (Phase 5.12) | n8n Code 노드의 sandbox가 기본적으로 `require('zlib')` 차단 → 환경변수로 허용 |
| 2026-03-02 | 발행 후 HTTP HEAD 검증 도입 (Phase 5.13) | 발행 URL을 HTTP HEAD로 검증, 403(비공개) 감지 시 `_fix_post_visibility()` API로 자동 공개 전환 시도 |
| 2026-03-02 | `_select_public_mode()` silent failure 대응 (Phase 5.13) | 기존: 공개 선택 실패 시 경고만 → 개선: 발행 후 HTTP 검증으로 실제 공개 상태 확인 + 자동 복구 |
| 2026-03-02 | `DailyPublishLimitError` 도입 (Phase 5.14) | 일일 15건 제한 도달 시 나머지 포스트를 실패 처리하지 않고 배치 중단 + 현재 포스트 발행대기 복원 |
| 2026-03-04 | SeleniumBase `user_data_dir` → `chromium_arg` 전환 (Phase 6) | SeleniumBase 4.47.1에서 `user_data_dir` 파라미터가 Chrome 실행 실패 유발 → `chromium_arg=f"--user-data-dir={path}"` 방식으로 우회 |
| 2026-03-04 | React fiber onChange 호출 방식 채택 (Phase 6) | DOM 클릭만으로는 React state 비갱신 → `__reactProps$` fiber에서 onChange 핸들러 직접 호출, 3단계 fallback (props→fiber tree→native event) |
| 2026-03-04 | XHR API 우선 + React UI fallback 순서 변경 (Phase 6) | XHR 직접 호출에서 `visibility: '20'` 명시적 전송이 공개 발행에 가장 신뢰도 높음 |
| 2026-03-05 | 내부 링크 전략 2 도입: published 키워드 직접 검색 (Phase 6) | `internal_link_keywords`↔published 키워드 매칭 실패 시 본문에서 published 키워드를 직접 검색하는 보조 전략 추가 |
| 2026-03-05 | CATEGORY_MAP 실제 Tistory ID로 갱신 (Phase 6) | 기존 ID 1152966~1152968이 블로그에 미존재 → category.json API로 실제 ID 확인: 용어→991463(배운것/용어정리), 비교/에러→966384(배운것) |
| 2026-03-05 | entryId URL 추출 + CWV rate limit 딜레이 (Phase 6) | Tistory post.json이 entryId null 반환 → URL 경로에서 추출; PageSpeed API 429 → 호출 간 3초/429시 10초 대기 |
| 2026-03-06 | 허브-스포크 InternalLinkService 도입 (Phase 6) | 카테고리만 보던 관련 글 선정 → 키워드 겹침 기반 스코어링 + 허브 글 우선순위로 내부 링크 품질 향상 |
| 2026-03-06 | 로그 기본 경로 `/var/log` → `logs/` 변경 (Phase 6) | macOS에서 PermissionError로 파일 로그 미생성 → 프로젝트 내 `logs/` + cli.py에서 PROJECT_ROOT 절대 경로 |
| 2026-03-06 | run_pipeline_b.sh PROJECT_DIR 경로 수정 (Phase 6) | `claudeagent/blog-automation` → `Core Web Vitals/blog-automation` — 실제 프로젝트 위치와 일치 |
