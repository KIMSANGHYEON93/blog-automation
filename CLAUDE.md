# Blog Automation DDD Project — Claude Code Configuration

## Project Overview
B2B IT 블로그 자동화 프로젝트의 Pipeline B를 DDD 4-Layer + TDD로 구축한다.
상세 설계: `process.md` (1,207줄) / 마스터 플랜: `masterplan_v2.3.md` (980줄)

## Architecture Rules (MANDATORY)
- Domain Layer (src/domain/): 외부 의존성 ZERO. 순수 Python만 허용
- Application Layer (src/application/): Domain만 import 가능. Infrastructure 직접 참조 금지
- Infrastructure Layer (src/infrastructure/): Domain의 Port 인터페이스를 구현
- Interface Layer (src/interface/): Composition Root. 유일하게 모든 레이어 import 가능
- 의존성 방향: Interface → Application → Domain ← Infrastructure
- 금지 패턴: Domain이 Infrastructure를 import하는 것은 절대 금지

## Import Validation Rule
```python
# ❌ FORBIDDEN (Domain → Infrastructure)
from src.infrastructure.persistence import google_sheets_repo

# ✅ CORRECT (Domain defines Port, Infrastructure implements)
from src.domain.ports.post_repository import PostRepository
```

## Directory Structure
```
src/
├── domain/
│   ├── __init__.py
│   ├── entities/post.py              # Post Entity + 상태 머신
│   ├── value_objects/
│   │   ├── __init__.py
│   │   ├── post_status.py            # PostStatus Enum (7 states)
│   │   ├── post_content.py           # PostContent VO (title, body, tags, category)
│   │   ├── publish_result.py         # PublishResult VO (success, url, error)
│   │   ├── column_index.py           # ColumnIndex VO (A-S mapping)
│   │   └── sheet_row_data.py         # SheetRowData VO
│   ├── ports/
│   │   ├── __init__.py
│   │   ├── post_repository.py        # PostRepository ABC
│   │   └── browser_port.py           # BrowserPort ABC
│   ├── services/
│   │   ├── __init__.py
│   │   └── publish_policy.py         # PublishPolicy domain service
│   └── exceptions.py                 # DomainError hierarchy
├── application/
│   ├── __init__.py
│   ├── use_cases/
│   │   ├── __init__.py
│   │   ├── publish_posts.py          # PublishPostsUseCase
│   │   └── reset_stuck_posts.py      # ResetStuckPostsUseCase
│   └── dto.py                        # PublishBatchResult DTO
├── infrastructure/
│   ├── __init__.py
│   ├── config.py                     # Settings (env-based)
│   ├── logging_setup.py              # Structured logging
│   ├── persistence/
│   │   ├── __init__.py
│   │   ├── column_map.py             # COL / COL_EXT constants
│   │   ├── google_sheets_repo.py     # GoogleSheetsPostRepository
│   │   └── in_memory_repo.py         # InMemoryPostRepository (test double)
│   └── browser/
│       ├── __init__.py
│       ├── dom_selectors.py           # SELECTORS dict
│       ├── js_injector.py             # safe_js_inject()
│       ├── human_typing.py            # human_type()
│       ├── kakao_auth.py              # KakaoAuthenticator
│       ├── tistory_editor.py          # TistoryEditorAdapter
│       ├── selenium_adapter.py        # SeleniumBrowserAdapter (implements BrowserPort)
│       └── mock_browser.py            # MockBrowserAdapter (test double)
└── interface/
    ├── __init__.py
    └── cli.py                         # Composition Root + __main__

tests/
├── conftest.py                        # shared fixtures
├── unit/
│   ├── domain/
│   │   ├── test_post_entity.py        # 15+ tests
│   │   ├── test_post_status.py
│   │   ├── test_post_content.py
│   │   ├── test_publish_result.py
│   │   └── test_publish_policy.py
│   └── application/
│       ├── test_publish_posts_use_case.py    # 8+ tests
│       └── test_reset_stuck_posts_use_case.py
├── integration/
│   ├── test_google_sheets_repo.py
│   └── test_selenium_adapter.py
└── e2e/
    └── test_full_publish_flow.py
```

## Sub-Agent Routing Rules

### Parallel dispatch (ALL conditions must be met):
- 3+ unrelated tasks or independent domains
- No shared state between tasks
- Clear file boundaries with no overlap

### Sequential dispatch (ANY condition triggers):
- Tasks have dependencies (B needs output from A)
- Shared files or state (merge conflict risk)
- Unclear scope (need to understand before proceeding)

## Agent Team Configuration
When working on this project with multiple agents, use these roles:

### domain-architect
- Scope: src/domain/, tests/unit/domain/
- Approach: TDD Inside-Out (Red → Green → Refactor)
- MUST write test FIRST, then implementation
- Zero external dependencies in Domain Layer

### infra-builder
- Scope: src/infrastructure/, tests/integration/
- Depends on: domain-architect completion (needs Port interfaces)
- Implements Port interfaces defined by domain-architect

### test-runner
- Scope: tests/, Makefile test commands
- Triggers: After each agent completes a module
- Runs: pytest + ruff + mypy
- Reports: coverage, failures, lint warnings

### quality-auditor
- Scope: Entire src/ and tests/
- Triggers: After all agents complete
- Validates: DDD layer rules, import direction, coverage thresholds

## TDD Cycle (MANDATORY for domain-architect)
1. RED: Write failing test first
2. GREEN: Write minimum code to pass
3. REFACTOR: Clean up while tests stay green
4. Each cycle must be a separate git commit

## Commit Message Convention
```
feat(domain): add PostStatus value object
test(domain): add PostStatus transition tests
feat(infra): implement GoogleSheetsPostRepository
fix(domain): handle edge case in mark_failed truncation
refactor(app): simplify PublishPostsUseCase error handling
```

## Quality Gates
- Unit test coverage (domain + application): ≥ 80%
- All tests pass: 100%
- Lint warnings (ruff): 0
- Type errors (mypy): 0
- Import rule violations: 0
