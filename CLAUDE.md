# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

B2B IT 블로그 자동화 시스템 — Pipeline B (콘텐츠 발행). DDD 4-Layer + Hexagonal Architecture로 구축.
- Pipeline A: n8n 워크플로우로 콘텐츠 생성 (01:00 AM cron)
- Pipeline B: Python/Selenium으로 Tistory 자동 발행 (09:00 AM cron)
- 상세 설계: `masterplan_v2.3.md` / 개발 이력: `process.md`

## Common Commands

```bash
# Install
pip install -e ".[dev]"

# Run Pipeline B
python -m src.interface.cli

# Unit tests (fast, no external services)
make test-unit

# Single test file
python -m pytest tests/unit/domain/test_post_entity.py -v

# Single test function
python -m pytest tests/unit/domain/test_post_entity.py::TestPostEntity::test_mark_publishing -v

# Integration tests (requires Google Sheets credentials + browser)
make test-integ

# Coverage (≥80% required for domain + application)
make coverage

# Lint + type check
make lint          # ruff check src/ tests/
make typecheck     # mypy src/ --ignore-missing-imports

# DDD layer violation check
make validate-ddd

# Full quality gate (all of the above)
make quality

# Auto-fix lint issues
ruff check --fix src/ tests/
```

## Architecture Rules (MANDATORY)

### DDD 4-Layer — Dependency Direction

```
Interface → Application → Domain ← Infrastructure
```

| Layer | Path | May Import | May NOT Import |
|-------|------|-----------|----------------|
| Domain | `src/domain/` | stdlib only (`typing`, `dataclasses`, `enum`, `abc`, `datetime`, `re`) | Application, Infrastructure, any external package |
| Application | `src/application/` | Domain | Infrastructure |
| Infrastructure | `src/infrastructure/` | Domain (implements Ports) | Application |
| Interface | `src/interface/cli.py` | All layers (Composition Root) | — |

Domain → Infrastructure import는 절대 금지. `make validate-ddd`로 검증.

### Port & Adapter Pattern

- **Ports** (Domain에 정의): `PostRepository` ABC, `BrowserPort` ABC
- **Adapters** (Infrastructure에서 구현): `GoogleSheetsPostRepository`, `SeleniumBrowserAdapter`
- **Test Doubles**: `InMemoryPostRepository`, `MockBrowserAdapter`
- Use Cases는 생성자 주입으로 Port 인터페이스만 받음

### Post State Machine

```
WAITING → GENERATING → PENDING → PUBLISHING → PUBLISHED
                                      ↓
                                    FAILED → (reset) → PENDING
```

`Post` entity가 상태 전이 규칙을 enforce함. 잘못된 전이 시 `InvalidStateTransitionError` 발생.

## Code Style

- Python 3.9+ (no walrus operator in 3.8 compat areas)
- Line length: 100 chars
- Ruff rules: E, F, W, I, N, UP, B, A, SIM
- Tests에서 `N802` (함수명 naming) 면제
- Value Objects: `@dataclass(frozen=True)`
- Use Cases: `XxxUseCase` 접미사, 생성자 DI
- Commit convention: `feat(domain):`, `test(app):`, `fix(infra):`, `refactor(app):` 등

## Quality Gates

| Gate | Threshold | Command |
|------|-----------|---------|
| Unit tests | 100% pass | `make test-unit` |
| Domain+App coverage | ≥ 80% | `make coverage` |
| Lint (ruff) | 0 warnings | `make lint` |
| Type check (mypy) | 0 errors | `make typecheck` |
| DDD layer violations | 0 | `make validate-ddd` |

## TDD Cycle (domain/application 개발 시)

1. **RED**: 실패하는 테스트 먼저 작성
2. **GREEN**: 테스트 통과하는 최소 코드 작성
3. **REFACTOR**: 테스트 유지하며 정리
4. 각 사이클을 별도 커밋으로 분리

## Agent Team Roles

| Role | Scope | Notes |
|------|-------|-------|
| `domain-architect` | `src/domain/`, `tests/unit/domain/` | TDD Inside-Out, 외부 의존성 ZERO |
| `infra-builder` | `src/application/`, `src/infrastructure/`, `src/interface/` | domain-architect 완료 후 시작, Port 구현 |
| `test-runner` | `tests/`, Makefile | 모듈 완성 후 트리거, pytest + ruff + mypy |
| `quality-auditor` | 전체 `src/`, `tests/` | 전체 완성 후, DDD 규칙 + 커버리지 검증 |

### Parallel vs Sequential Dispatch

- **Parallel**: 3+ 독립 태스크, 공유 상태 없음, 파일 경계 명확
- **Sequential**: 의존관계 있음, 공유 파일 있음, 범위 불분명

## Key Environment Variables

`.env` 파일 필요 (`.env.example` 참고):
- `KAKAO_ID`, `KAKAO_PW` — Tistory 로그인용 카카오 계정
- `TISTORY_BLOG` — 블로그명
- `GOOGLE_CREDS` — 서비스 계정 JSON 키 경로
- `SHEET_NAME` — Google Sheets 스프레드시트 이름
- `MAX_POSTS`, `HEADLESS`, `MIN_DELAY`, `MAX_DELAY` — 발행 파라미터
