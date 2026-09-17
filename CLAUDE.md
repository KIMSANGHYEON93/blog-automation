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
python -m src.interface.cli --discover-keywords [--auto-register]
python -m src.interface.cli --sync-categories [--auto-update]
python -m src.interface.cli --set-thumbnails [--thumbnail-max N]
python -m src.interface.cli --publish-pages      # AdSense 필수 페이지
```

운영 환경에서는 crontab이 모드별로 따로 실행함(08:30 recover-failed, 09:00 발행, 10:00 revise, 14:00 check-index, 14:30 submit-index, 15:00 dashboard). `run_pipeline_b.sh`는 `.pipeline_b.lock` 디렉토리 락으로 동시 실행을 막고, 끝나면 남은 Chrome 프로세스를 정리함. 로그는 `logs/`.

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
