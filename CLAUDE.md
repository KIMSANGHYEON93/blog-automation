# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

B2B IT 블로그(Tistory) 자동화 시스템. Google Sheets(`keyword_calendar_v2`)가 두 파이프라인 사이의 DB/상태 저장소 역할.
- **Pipeline A** (`n8n/`, Docker): 키워드 → SERP → LLM 콘텐츠 생성 → 교차 검증 → 시트에 `발행대기`로 기록
- **Pipeline B** (`src/`, Python + SeleniumBase): 시트에서 `발행대기` 글을 읽어 카카오 로그인 → Tistory 발행 → URL/상태 기록. SEO 운영 작업(색인, CWV, 사이트맵, 썸네일)도 담당
- 상세 설계: `masterplan_v2.3.md` / 개발 이력: `process.md` / 운영 가이드: `docs/EXECUTION_GUIDE.md`, `docs/SHEETS_GUIDE.md`

## Common Commands

```bash
pip install -e ".[dev]"

# Tests
make test-unit                  # tests/unit/ (외부 서비스 불필요)
make test-integ                 # Google Sheets 자격증명 + 브라우저 필요
make test-e2e                   # 전체 발행 흐름
python -m pytest tests/unit/domain/test_post_entity.py -v
python -m pytest tests/unit/domain/test_post_entity.py::TestPostEntity::test_mark_publishing -v

# Quality
make lint                       # ruff check src/ tests/
make typecheck                  # mypy src/ --ignore-missing-imports
make coverage                   # domain+application ≥ 80% (--cov-fail-under)
make validate-ddd               # grep 기반 계층 import 위반 검사
make quality                    # test-unit + coverage + lint + typecheck + validate-ddd
ruff check --fix src/ tests/

# n8n (Pipeline A)
docker compose up -d            # localhost:5678
```

### CLI (`src/interface/cli.py`) — 플래그 하나당 모드 하나

```bash
python -m src.interface.cli                      # 기본: 고스트 복구 → 카테고리 자동분류 → 발행 → CWV 점검
python -m src.interface.cli --revise             # 수정대기 → 기존 Tistory 글 업데이트
python -m src.interface.cli --recover-failed [--force-reset]
python -m src.interface.cli --check-index        # 미색인 발행완료 글 → 수정대기
python -m src.interface.cli --submit-index       # Google Indexing API 제출
python -m src.interface.cli --generate-sitemap
python -m src.interface.cli --status             # (= --dashboard, crontab 호환 alias)
python -m src.interface.cli --discover-keywords [--auto-register] [--discover-days N]
python -m src.interface.cli --generate-term-keywords [--auto-register]  # 볼트 용어 → 키워드
python -m src.interface.cli --sync-categories [--auto-update]
python -m src.interface.cli --set-thumbnails [--thumbnail-max N]
python -m src.interface.cli --publish-pages      # AdSense 필수 페이지
```

운영 환경에서는 launchd(`~/Library/LaunchAgents/com.blog-automation.*.plist`)가 모드별로 실행함(00:00 discover-keywords, 08:30 recover-failed, 09:00 발행, 10:00 revise, 14:00 check-index, 14:30 submit-index, 15:00 dashboard, 일요일 23:00 sync-brain-terms). crontab은 쓰지 않음(중복 실행 방지). plist는 `~/bin/run_pipeline_b.sh`·`~/bin/run_dashboard.sh`를 호출하는데, 이 둘은 저장소의 같은 이름 스크립트를 가리키는 심볼릭 링크이므로 **저장소 스크립트를 고치면 곧바로 운영에 반영됨**. launchd는 셸 초기화를 하지 않으므로 스크립트는 `PROJECT_DIR`/`PYTHON`에 절대경로 기본값을 쓰고, `BLOG_PROJECT_DIR`/`BLOG_PYTHON`으로 덮어쓸 수 있음. `run_pipeline_b.sh`는 `.pipeline_b.lock` 디렉토리 락으로 동시 실행을 막고, 끝나면 남은 Chrome 프로세스를 정리함. 로그는 `logs/`.

### 관리자 대시보드 (`src/interface/web/`) — 수동 발행

자동 발행과 별개로, 로그인한 관리자가 게시물 현황을 보고 `발행대기` 글을 1건씩 수동 발행하는 로컬 웹앱 (Flask, 두 번째 Composition Root).

```bash
python -m src.interface.web hash-password   # .env: DASHBOARD_ADMIN_PASSWORD_HASH='...'
python -m src.interface.web gen-secret      # .env: DASHBOARD_SECRET_KEY=...
make dashboard                              # = python -m src.interface.web → http://127.0.0.1:8787
python -m pytest tests/unit/interface -v    # 인증·CSRF·라우트·작업 실행기 테스트
```

- 수동 발행은 `PublishSelectedPostUseCase`: 자동 발행과 같은 규칙(본문 3000자·품질 70점·일일 쿼터·중복 키워드·내부 링크)을 적용하되, 거부 시 게시물 상태를 바꾸지 않음. 발행 불가 사유는 `publish_blockers()`로 목록/상세 화면에도 표시
- 자동 파이프라인과 같은 `.browser_data`를 쓰므로 `DirectoryPipelineLock`(`run_pipeline_b.sh`와 같은 `.pipeline_b.lock`)을 잡은 뒤에만 브라우저를 엶. 자동 실행 중이면 거부
- 발행은 `PublishJobRunner` 백그라운드 스레드에서 동시에 1건만 실행, 작업 상태는 메모리에만 있음(서버 재시작 시 사라짐). 작업 페이지는 meta refresh로 갱신(CSP상 JS 없음)
- 보안: 모든 페이지 로그인 필요, 모든 POST CSRF 검증, IP별 로그인 5회/15분 제한, `127.0.0.1` 바인딩 기본(외부 바인딩은 `DASHBOARD_ALLOW_REMOTE=true` 필요 — HTTP라 HTTPS 프록시 뒤에서만)
- launchd에 등록하지 않음 — 필요할 때 직접 실행

## Architecture

DDD 4-Layer + Hexagonal. 의존 방향: `Interface → Application → Domain ← Infrastructure`

| Layer | Path | May Import | May NOT Import |
|-------|------|-----------|----------------|
| Domain | `src/domain/` | stdlib only | Application, Infrastructure, 외부 패키지 |
| Application | `src/application/` | Domain | Infrastructure |
| Infrastructure | `src/infrastructure/` | Domain (Port 구현) | Application |
| Interface | `src/interface/cli.py` | 전부 (Composition Root) | — |

`make validate-ddd`는 `src.infrastructure`/`src.application` import 문자열만 grep함 — **Domain에서 외부 패키지를 import해도 잡지 못하므로** 직접 확인할 것.

### 구성 요소 위치

- **Ports** (`src/domain/ports/`): `PostRepository`, `BrowserPort`, SEO/Sitemap/Keyword/Notification/ImageGeneration/ThumbnailUpload/CategorySync/SiteProfile 포트
- **Adapters** (`src/infrastructure/`): `persistence/`(Google Sheets, InMemory, JSON site profile), `browser/`(Selenium/Tistory), `seo/`(PageSpeed CWV, GSC 색인, Indexing API, sitemap), `image/`(Pollinations 기본, `OPENAI_API_KEY` 있으면 DALL-E), `notification/`(Slack/Telegram/Null)
- **Test doubles**: `InMemoryPostRepository`(`persistence/in_memory_repo.py`), `MockBrowserAdapter`(`browser/mock_browser.py`)
- **Use Cases** (`src/application/use_cases/`): CLI 모드와 거의 1:1 대응. 생성자 DI로 Port만 받음
- 의존성 조립은 모두 `cli.py`의 `_revise`, `_check_index` 등 모드별 함수와 `_main_inner` 안에서 이루어짐

### Tistory 발행 (`src/infrastructure/browser/`)

`SeleniumBrowserAdapter`(BrowserPort) → `tistory_editor`(오케스트레이터)가 여러 모듈을 조합: `kakao_auth`(로그인, 세션은 `.browser_data/` 유지), `api_publisher`(발행 + 재시도), `content_injector`/`form_filler`/`js_injector`(에디터 조작), `markdown_converter` + `html_transformer`(Markdown→HTML, lazy loading, FAQ JSON-LD), `publish_verifier`(URL/entry_id 추출), `dom_selectors`(셀렉터 fallback 체인).

### Post 상태 머신 (`src/domain/entities/post.py`)

`PostStatus` enum의 **값은 한글 문자열이고 시트 J열에 그대로 저장됨** (`대기`, `생성중`, `발행대기`, `발행중`, `발행완료`, `발행실패`, `보류`, `수정대기`, `수정중`).

```
WAITING → GENERATING → PENDING → PUBLISHING → PUBLISHED → REVISION_PENDING → REVISING → PUBLISHED
                          │          │  ↑ ghost reset                              ↑ ghost reset
                          ↓          ↓
                        HOLD       FAILED → PENDING or REVISION_PENDING (recover)
```

- 잘못된 전이 시 `InvalidStatusTransitionError` (`src/domain/exceptions.py`)
- WAITING/GENERATING은 n8n(Pipeline A)이 시트에 직접 기록함
- `is_publishable()`: PENDING + 본문 ≥ 3000자 + `quality_score ≥ 70`
- 고스트 복구(`ResetStuckPostsUseCase`): 중간에 끊긴 실행 때문에 남은 `발행중`/`수정중` 글을 되돌림

### Google Sheets 스키마

컬럼 번호는 `src/infrastructure/persistence/column_map.py`의 `COL` dict에만 정의되어 있음(1-based, A~AH). 시트 컬럼을 바꿀 때는 이 파일과 n8n 워크플로우의 Sheets 노드를 함께 수정해야 함.

### Pipeline A (`n8n/`)

- `workflow_complete.json`이 메인 워크플로우, `workflow_keyword_research.json`은 키워드 리서치용
- `code_nodes/*.js`는 Code 노드의 원본 소스이고, 워크플로우 JSON의 `jsCode` 필드에 **인라인 복사**되어 있음(동기화 스크립트 없음). `.js`만 고치면 n8n에 반영되지 않으므로 JSON도 같이 수정하거나 n8n UI에 다시 붙여넣을 것
- 프롬프트(`prompts/`): 용어(a) / 비교(b) / 에러해결(c)은 `route_prompt.js`가 선택하고, 교차 검증은 d. `*_v1.md`는 이전 버전
- **키워드 발굴 조회 기간**: `DEFAULT_LOOKBACK_DAYS = 90`. 저트래픽 블로그에서 28일 창은 쿼리별 노출이 흩어져 `min_impressions=5`를 아무도 못 넘긴다(2026-09-23 실측: 28일 0건 / 90일 10건). `--discover-days`로 조절
- **로그인은 세션 재사용이 먼저다**: `SeleniumBrowserAdapter.login()`이 `.browser_data/tistory_session.json`(0600)의 쿠키를 주입해 관리 페이지 접근으로 검증하고, 실패할 때만 카카오 OAuth를 탄다. 매 실행이 OAuth를 타면 카카오 이상탐지가 2FA를 띄운다(2026-09-23 실측: 기동 7회에 2FA 3회). 세션 파일에는 티스토리 도메인 쿠키만 담는다 — 카카오 `_kau`는 유출 시 피해가 크고 tiara는 추적용이라 제외
- **로그인 실패는 예외다**: `browser.login()` 실패 시 `LoginFailedError`가 올라가 종료코드가 0이 아니게 되고 알림이 나간다. 조용히 `return`하면 launchd가 성공으로 기록해 장애가 몇 달간 묻힌다(2026-05~09 실제 사례). 2FA 감지 시에도 즉시 알림이 나가고 승인 대기는 300초
- **LLM 토큰 예산**: Gemini 3.x는 추론(thoughts) 토큰을 먼저 쓰므로 `maxTokens`가 빠듯하면 응답 JSON이 `MAX_TOKENS`로 잘리고, 파서가 품질 0점으로 처리해 발행이 막힌다(검증 호출 800 → 4096으로 수정). 모델 교체 시 실행 로그의 `finishReason` 확인
- JSON의 `jsCode`에 코드를 넣을 때 줄바꿈이 이중 이스케이프되면 코드 전체가 주석 한 줄이 되어 조용히 죽는다. 넣은 뒤 `node --check`로 문법 확인
- 키워드 자동 등록: launchd 00:00이 `--auto-register --discover-limit 3`으로 실행. 등록 1건당 Pipeline A가 SerpAPI를 1회 쓰므로(무료 플랜 월 250건) 건수 조절은 `--discover-limit`으로
- **AI-Brain 용어 → 키워드**: `--generate-term-keywords`는 `AI브레인용어` 탭에서 키워드를 역방향 생성한다. GSC 발굴은 '이미 노출된 쿼리'만 주므로 트래픽 없는 주제가 영원히 빠지는데(트래픽 없음 → 키워드 없음 → 글 없음 → 트래픽 없음), 볼트 용어는 트래픽과 무관한 시드라 그 루프를 끊는다. `혼동포인트`의 `A ≠ B` 형식(376/381건)에서 비교 글 주제가 나온다. 실측 381건 → 후보 468건. GSC 발굴과 같은 중복·B2C 필터를 쓴다 — 기준이 갈리면 Pipeline A가 중복으로 버린다
- **AI-Brain 용어 주입**: 시트 `AI브레인용어` 탭(용어·별칭·한줄정의·혼동포인트·출처)을 `Sheets Read (Brain Terms)`가 읽고, `Route Prompt`가 키워드와 매칭되는 용어를 최대 3건까지 user_message에 넣는다. 원본은 Google Drive 옵시디언 볼트 `AI-Brain/10_Terms`이고, `python scripts/sync_brain_terms.py`(`.env`의 `BRAIN_VAULT_FOLDER_ID`, `--dry-run` 지원)로 탭을 갱신한다 — 서비스 계정에 볼트 폴더가 읽기 권한으로 공유돼 있어야 함. n8n은 병렬 브랜치 실행 순서를 보장하지 않으므로 용어 노드는 `Reduce to Trigger → Sheets Read (Brain Terms) → Reduce Brain Terms → Sheets Read (Status=대기)`로 **직렬 배치**하고, 축약 노드가 뒤 노드의 중복 실행을 막는다

### 설정

- `.env` (`.env.example` 참고) → `src/infrastructure/config.py`의 `Config.from_env()`. `config.validate()`는 기본 발행 모드에서만 호출됨
- 기능 플래그: `CWV_CHECK`(기본 true), `RETRY_FAILED`(기본 false). 알림은 `SLACK_WEBHOOK_URL` 또는 `TELEGRAM_*` 중 하나
- `site_profile.json`: 카테고리 매핑 + 키워드 분류 규칙. 파일이 없으면 기본값으로 동작

## Code Style

- Python 3.9 타깃(ruff `py39`, mypy 3.9). `X | None` 문법을 쓰려면 `from __future__ import annotations` 필요(기존 파일 방식)
- Line length 100, ruff rules E/F/W/I/N/UP/B/A/SIM, tests는 `N802` 면제
- Value Objects: `@dataclass(frozen=True)` / Use Cases: `XxxUseCase` 접미사 + 생성자 DI
- 로그/사용자 메시지는 한국어
- Commit: `feat(domain):`, `test(app):`, `fix(infra):`, `refactor(app):`, `fix(cli):` 등

## TDD & Quality Gates

domain/application 작업은 RED → GREEN → REFACTOR 순서로 하고, 사이클마다 커밋을 따로 남김. 완료 전 `make quality` 통과 필수 (unit 100% pass, domain+app coverage ≥ 80%, ruff 0, mypy 0, DDD 위반 0).

## Agent Team Roles (`.claude/agents/`)

| Role | Scope |
|------|-------|
| `domain-architect` | `src/domain/`, `tests/unit/domain/` — TDD Inside-Out |
| `infra-builder` | `src/application/`, `src/infrastructure/`, `src/interface/` — domain 완료 후 |
| `test-runner` | 코드 변경 후 pytest + ruff + mypy 실행 |
| `quality-auditor` | 전체 완료 후 DDD 규칙 + 커버리지 검증 |

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
