---
name: blog-automation-conventions
description: Development conventions and patterns for blog-automation. Python project with conventional commits.
---

# Blog Automation Conventions

> Generated from [KIMSANGHYEON93/blog-automation](https://github.com/KIMSANGHYEON93/blog-automation) on 2026-03-22

## Overview

This skill teaches Claude the development patterns and conventions used in blog-automation.

## Tech Stack

- **Primary Language**: Python
- **Architecture**: hybrid module organization
- **Test Location**: separate

## When to Use This Skill

Activate this skill when:
- Making changes to this repository
- Adding new features following established patterns
- Writing tests that match project conventions
- Creating commits with proper message format

## Commit Conventions

Follow these commit message conventions based on 108 analyzed commits.

### Commit Style: Conventional Commits

### Prefixes Used

- `feat`
- `docs`
- `fix`
- `refactor`
- `chore`

### Message Guidelines

- Average message length: ~59 characters
- Keep first line concise and descriptive
- Use imperative mood ("Add feature" not "Added feature")


*Commit message example*

```text
fix(infra): set_script_timeout을 sb.open() 이후로 이동하여 첫 시도 timeout 해결
```

*Commit message example*

```text
feat: 카테고리 자동 분류 + 홈주제(daumLike) 발행 지원
```

*Commit message example*

```text
chore(n8n): sync code_nodes into workflow_complete.json jsCode fields
```

*Commit message example*

```text
docs: add full cron schedule and update run_pipeline_b.sh for sub-commands
```

*Commit message example*

```text
refactor(infra): update external callers for tistory_editor split
```

*Commit message example*

```text
fix(n8n): Sheets Write reads validated content/references from URL Validation node
```

*Commit message example*

```text
feat(n8n): HTTP HEAD validation + SERP cross-reference + dead URL cleanup
```

*Commit message example*

```text
feat(n8n): pass serp_urls pool in user_message for LLM
```

## Architecture

### Project Structure: Single Package

This project uses **hybrid** module organization.

### Source Layout

```
src/
├── application/
├── domain/
├── infrastructure/
├── interface/
```

### Configuration Files

- `docker-compose.yml`

### Guidelines

- This project uses a hybrid organization
- Follow existing patterns when adding new code

## Code Style

### Language: Python

### Naming Conventions

| Element | Convention |
|---------|------------|
| Files | snake_case |
| Functions | camelCase |
| Classes | PascalCase |
| Constants | SCREAMING_SNAKE_CASE |

### Import Style: Relative Imports

### Export Style: Named Exports


*Preferred import style*

```typescript
// Use relative imports
import { Button } from '../components/Button'
import { useAuth } from './hooks/useAuth'
```

*Preferred export style*

```typescript
// Use named exports
export function calculateTotal() { ... }
export const TAX_RATE = 0.1
export interface Order { ... }
```

## Error Handling

### Error Handling Style: Try-Catch Blocks


*Standard error handling pattern*

```typescript
try {
  const result = await riskyOperation()
  return result
} catch (error) {
  console.error('Operation failed:', error)
  throw new Error('User-friendly message')
}
```

## Common Workflows

These workflows were detected from analyzing commit patterns.

### Feature Development

Standard feature implementation workflow

**Frequency**: ~17 times per month

**Steps**:
1. Add feature implementation
2. Add tests for feature
3. Update documentation

**Files typically involved**:
- `**/*.test.*`
- `**/api/**`

**Example commit sequence**:
```
feat(domain): site_profile.json 동적 카테고리 관리 + 자동 분류
feat(infra): 하위 카테고리 재귀 파싱 + 통합 테스트
fix(infra): cron Pipeline B 경로 수정
```

### Refactoring

Code refactoring and cleanup workflow

**Frequency**: ~8 times per month

**Steps**:
1. Ensure tests pass before refactor
2. Refactor code structure
3. Verify tests still pass

**Files typically involved**:
- `src/**/*`

**Example commit sequence**:
```
docs: finalize documentation and add remaining source files for GitHub push
docs: 팀 내부 공유용 프로젝트 발표 대본 작성
feat(scripts): 키워드 30건 일괄 추가 스크립트
```

### N8n Prompt And Code Node Update

Update or enhance n8n workflow prompts and code nodes to improve content quality gates, prompt requirements, or workflow logic.

**Frequency**: ~4 times per month

**Steps**:
1. Edit one or more prompt markdown files in n8n/prompts/ (e.g., to raise content length, add new sections, or clarify instructions)
2. Edit or add code node JS files in n8n/code_nodes/ (e.g., to add validation, parsing, or enrichment logic)
3. Update n8n/workflow_complete.json to sync with new code nodes or prompt logic

**Files typically involved**:
- `n8n/prompts/prompt_a_terminology.md`
- `n8n/prompts/prompt_b_comparison.md`
- `n8n/prompts/prompt_c_troubleshooting.md`
- `n8n/prompts/prompt_d_verification.md`
- `n8n/code_nodes/*.js`
- `n8n/workflow_complete.json`

**Example commit sequence**:
```
Edit one or more prompt markdown files in n8n/prompts/ (e.g., to raise content length, add new sections, or clarify instructions)
Edit or add code node JS files in n8n/code_nodes/ (e.g., to add validation, parsing, or enrichment logic)
Update n8n/workflow_complete.json to sync with new code nodes or prompt logic
```

### Domain Entity Or Policy Gate Enhancement

Add or adjust domain-level publishability gates (e.g., content length, quality score) and synchronize with corresponding tests.

**Frequency**: ~2 times per month

**Steps**:
1. Edit src/domain/entities/post.py to add or change publishability logic (e.g., min content length, quality score)
2. Edit or add tests in tests/unit/domain/ and tests/unit/application/ to cover new rules
3. If needed, update src/infrastructure/persistence/ or related adapters to support new fields

**Files typically involved**:
- `src/domain/entities/post.py`
- `tests/unit/domain/test_post_entity.py`
- `tests/unit/domain/test_publish_policy.py`
- `tests/unit/application/test_publish_posts_usecase.py`
- `src/infrastructure/persistence/google_sheets_repo.py`

**Example commit sequence**:
```
Edit src/domain/entities/post.py to add or change publishability logic (e.g., min content length, quality score)
Edit or add tests in tests/unit/domain/ and tests/unit/application/ to cover new rules
If needed, update src/infrastructure/persistence/ or related adapters to support new fields
```

### Infrastructure Module Extraction And Refactor

Split a large infrastructure module (e.g., tistory_editor.py) into multiple focused submodules, update imports, and adjust tests.

**Frequency**: ~1 times per month

**Steps**:
1. Extract new submodules from the large file (e.g., create api_publisher.py, publish_verifier.py, etc.)
2. Update the original orchestrator module to delegate to submodules
3. Update all external callers to import from new submodules
4. Update or add tests to use new imports and structure

**Files typically involved**:
- `src/infrastructure/browser/tistory_editor.py`
- `src/infrastructure/browser/api_publisher.py`
- `src/infrastructure/browser/publish_verifier.py`
- `src/infrastructure/browser/content_injector.py`
- `src/infrastructure/browser/form_filler.py`
- `src/infrastructure/browser/html_transformer.py`
- `src/infrastructure/browser/markdown_converter.py`
- `src/infrastructure/browser/adsense_pages.py`
- `tests/unit/infrastructure/test_markdown_to_html.py`
- `tests/unit/infrastructure/test_thumbnail_extraction.py`

**Example commit sequence**:
```
Extract new submodules from the large file (e.g., create api_publisher.py, publish_verifier.py, etc.)
Update the original orchestrator module to delegate to submodules
Update all external callers to import from new submodules
Update or add tests to use new imports and structure
```

### Application Service Extraction And Di Refactor

Extract a shared application service (e.g., InternalLinkEnricher), inject it via DI into use cases, and update related tests.

**Frequency**: ~1 times per month

**Steps**:
1. Extract new service class into src/application/services/
2. Update use cases in src/application/use_cases/ to accept the service via constructor injection
3. Update CLI composition root to assemble dependencies
4. Update or add unit tests for both the new service and affected use cases

**Files typically involved**:
- `src/application/services/internal_link_enricher.py`
- `src/application/use_cases/publish_posts.py`
- `src/application/use_cases/revise_posts.py`
- `src/interface/cli.py`
- `tests/unit/application/test_internal_link_enricher.py`
- `tests/unit/application/test_publish_posts_usecase.py`
- `tests/unit/application/test_revise_posts_usecase.py`

**Example commit sequence**:
```
Extract new service class into src/application/services/
Update use cases in src/application/use_cases/ to accept the service via constructor injection
Update CLI composition root to assemble dependencies
Update or add unit tests for both the new service and affected use cases
```

### Category Management And Auto Classification Enhancement

Enhance category management by updating site_profile.json, value objects, adapters, and tests to support new categories or classification logic.

**Frequency**: ~2 times per month

**Steps**:
1. Edit site_profile.json to add or reorder categories and patterns
2. Update src/domain/value_objects/site_profile.py and related adapters
3. Update src/infrastructure/persistence/json_site_profile.py and in_memory_repo.py
4. Update or add use cases for classification and syncing
5. Update or add tests for new logic

**Files typically involved**:
- `site_profile.json`
- `src/domain/value_objects/site_profile.py`
- `src/infrastructure/persistence/json_site_profile.py`
- `src/infrastructure/persistence/in_memory_repo.py`
- `src/application/use_cases/classify_category.py`
- `src/application/use_cases/sync_categories.py`
- `src/domain/services/category_classification.py`
- `src/domain/ports/site_profile_port.py`
- `src/infrastructure/browser/category_sync_adapter.py`
- `tests/unit/application/test_classify_category.py`
- `tests/unit/application/test_sync_categories.py`
- `tests/unit/domain/test_category_classification.py`
- `tests/unit/domain/test_site_profile.py`
- `tests/unit/infrastructure/test_json_site_profile.py`

**Example commit sequence**:
```
Edit site_profile.json to add or reorder categories and patterns
Update src/domain/value_objects/site_profile.py and related adapters
Update src/infrastructure/persistence/json_site_profile.py and in_memory_repo.py
Update or add use cases for classification and syncing
Update or add tests for new logic
```

### Documentation And Execution Guide Update

Update documentation and execution guides, often alongside changes to scripts or automation entrypoints.

**Frequency**: ~2 times per month

**Steps**:
1. Edit or add markdown files in docs/ (e.g., EXECUTION_GUIDE.md, SHEETS_GUIDE.md)
2. Edit README.md and other top-level docs
3. Update or add shell scripts (e.g., run_pipeline_b.sh, run_dashboard.sh) to match new documented flows

**Files typically involved**:
- `docs/EXECUTION_GUIDE.md`
- `docs/SHEETS_GUIDE.md`
- `README.md`
- `run_pipeline_b.sh`
- `run_dashboard.sh`

**Example commit sequence**:
```
Edit or add markdown files in docs/ (e.g., EXECUTION_GUIDE.md, SHEETS_GUIDE.md)
Edit README.md and other top-level docs
Update or add shell scripts (e.g., run_pipeline_b.sh, run_dashboard.sh) to match new documented flows
```


## Best Practices

Based on analysis of the codebase, follow these practices:

### Do

- Use conventional commit format (feat:, fix:, etc.)
- Use snake_case for file names
- Prefer named exports

### Don't

- Don't write vague commit messages
- Don't deviate from established patterns without discussion

---

*This skill was auto-generated by [ECC Tools](https://ecc.tools). Review and customize as needed for your team.*
