# B2B IT 블로그 자동화 — 개발 프로세스 추적

> **문서 용도**: 실행 진행 추적 (마스터 플랜 `masterplan_v2.3.md`의 실행 로그)
> **최종 갱신**: 2026-02-28

---

## 현재 상태

| 항목 | 값 |
|------|---|
| **현재 Phase** | Phase 2.5 완료 → Phase 3 대기 |
| **단위 테스트** | 66건 통과 (Domain + Application) |
| **통합 테스트** | 9건 통과 (GoogleSheets 6 + Selenium 3) |
| **E2E 테스트** | 2건 스킵 (환경변수 미설정) |
| **전체 테스트** | 75건 통과, 2건 스킵 |
| **커버리지** | 92.05% (domain + application) |
| **ruff** | 0 errors |
| **mypy** | 0 errors |

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

## 다음 진행 단계

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

### Step 4: 파이프라인 A 구축 (Phase 3)

| # | 항목 | 설명 |
|---|------|------|
| 3.1 | n8n 워크플로우 조립 | Schedule Trigger → Sheets Read → SerpAPI → Claude Sonnet → Haiku → Sheets Update |
| 3.2 | 마스터 프롬프트 주입 | 프롬프트 A/B/C를 System Message에 세팅 |
| 3.3 | 교차 검증 로직 | Haiku 2항목(is_accurate, is_logical), Temperature=0 |
| 3.4 | JSON 파싱 에러 핸들링 | 실패 시 Status="검수필요" 분기 |
| 3.5 | 파이프라인 A 단독 테스트 | "대기" 키워드 → 수동 트리거 → "발행대기" 확인 |

### Step 5: E2E 통합 테스트 (Phase 3.5)

| # | 항목 |
|---|------|
| 3.5.1 | 테스트 키워드 3건 입력 (용어+비교+에러) |
| 3.5.2 | n8n 수동 트리거 → 3건 모두 "발행대기" 전이 |
| 3.5.5 | DDD 워커 → 3건 발행/임시저장 |
| 3.5.13 | `pytest tests/e2e/ -v` → 2건 통과 |

### Step 6: Go-Live (Phase 4)

| # | 항목 |
|---|------|
| 4.1 | n8n Schedule Trigger 활성화 (01:00 AM) |
| 4.2 | Cronjob 등록: `python3 -m src.interface.cli` (09:00 AM) |
| 4.3 | 첫 자동 실행 확인 |
| 4.5 | 레거시 `tistory_publisher.py` → `legacy/` 이동 |

---

## 의사결정 로그 (Phase 2.5)

| 일자 | 결정 사항 | 근거 |
|------|----------|------|
| 2026-02-28 | `_is_tistory_logged_in()` hostname 기반 판별로 변경 | OAuth redirect URL query param에서 false positive 발생 |
| 2026-02-28 | 카카오 버튼 클릭 후 URL 안정화 폴링 (최대 15초) | 고정 sleep 3초로는 2FA 리다이렉트 완료 보장 불가 |
| 2026-02-28 | `cli.py`에 `user_data_dir=".browser_data"` 추가 | 쿠키 영속화로 2FA 반복 방지, test_login.py와 동작 일치 |
