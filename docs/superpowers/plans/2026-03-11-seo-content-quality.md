# Phase A: SEO Content Quality Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade content quality to meet Google E-E-A-T standards — enhanced prompts (3000+ chars), length/depth gates, and duplicate detection.

**Architecture:** Pipeline A (n8n) handles content generation and verification; Pipeline B (Python/DDD) handles publishing. Changes span both pipelines: prompt files, JS code nodes, verification prompt, Post entity, and tests.

**Tech Stack:** JavaScript (n8n code nodes), Python 3.9+ (DDD 4-Layer), Markdown (prompts)

**Spec:** `docs/superpowers/specs/2026-03-11-seo-growth-strategy-design.md` — Phase A only

---

## Chunk 1: Gates & Detection (Code Changes)

### Task 1: Backup Existing Prompts

**Files:**
- Copy: `n8n/prompts/prompt_a_terminology.md` → `n8n/prompts/prompt_a_terminology_v1.md`
- Copy: `n8n/prompts/prompt_b_comparison.md` → `n8n/prompts/prompt_b_comparison_v1.md`
- Copy: `n8n/prompts/prompt_c_troubleshooting.md` → `n8n/prompts/prompt_c_troubleshooting_v1.md`

- [ ] **Step 1: Copy all three prompt files with _v1 suffix**

```bash
cd blog-automation
cp n8n/prompts/prompt_a_terminology.md n8n/prompts/prompt_a_terminology_v1.md
cp n8n/prompts/prompt_b_comparison.md n8n/prompts/prompt_b_comparison_v1.md
cp n8n/prompts/prompt_c_troubleshooting.md n8n/prompts/prompt_c_troubleshooting_v1.md
```

- [ ] **Step 2: Verify copies exist and match originals**

```bash
diff n8n/prompts/prompt_a_terminology.md n8n/prompts/prompt_a_terminology_v1.md
diff n8n/prompts/prompt_b_comparison.md n8n/prompts/prompt_b_comparison_v1.md
diff n8n/prompts/prompt_c_troubleshooting.md n8n/prompts/prompt_c_troubleshooting_v1.md
```

Expected: No diff output (files are identical).

- [ ] **Step 3: Commit**

```bash
git add n8n/prompts/*_v1.md
git commit -m "chore: backup existing prompts as v1 before SEO enhancement"
```

---

### Task 2: A2 Pipeline A — Length/Depth Gates

**Files:**
- Modify: `n8n/code_nodes/validate_structure.js` (add MIN_CONTENT_LENGTH 3000 check)
- Modify: `n8n/prompts/prompt_d_verification.md` (add is_in_depth as 5th item)
- Modify: `n8n/code_nodes/parse_verification.js` (add isInDepth to passed condition)

- [ ] **Step 1: Add MIN_CONTENT_LENGTH gate to validate_structure.js**

After the existing `issues` array declaration (line 12) and before the H2 check (line 14), add:

```javascript
// 0. Content length check
const MIN_CONTENT_LENGTH = 3000;
if (content.length < MIN_CONTENT_LENGTH) {
  issues.push(`본문 길이 부족: ${content.length}자 (최소 ${MIN_CONTENT_LENGTH}자)`);
}
```

- [ ] **Step 2: Add is_in_depth to prompt_d_verification.md**

After the existing 4th item (`is_useful`), add a 5th verification item:

```markdown
5. **is_in_depth** (깊이): 본문이 주제에 대해 충분한 깊이로 설명하고 있는가?
   - 단순 나열이 아닌 분석/설명이 포함되어 있는가?
   - 비교표, 코드 블록, 또는 체크리스트가 1개 이상 포함되어 있는가?
   - 실무 시나리오나 구체적 사례가 2개 이상 포함되어 있는가?
   - 위 조건 중 2개 이상 미충족 → false
```

Also update the JSON output example to include `"is_in_depth": true`.

Also update the intro text: "정확히 네 항목" → "정확히 다섯 항목"

- [ ] **Step 3: Add isInDepth to parse_verification.js passed condition**

After line 99 (`const isUseful = ...`), add:

```javascript
const isInDepth = typeof result.is_in_depth === "boolean" ? result.is_in_depth : true;
```

Update the `passed` condition (line 102-107) to include `isInDepth`:

```javascript
const passed = result.is_accurate === true
  && result.is_logical === true
  && isComplete === true
  && isUseful === true
  && isInDepth === true
  && qualityScore >= MIN_QUALITY_SCORE;
```

Also add `is_in_depth: isInDepth` to the verification output object.

- [ ] **Step 4: Verify files are syntactically valid**

```bash
node -c n8n/code_nodes/validate_structure.js
node -c n8n/code_nodes/parse_verification.js
```

Expected: No syntax errors.

- [ ] **Step 5: Commit**

```bash
git add n8n/code_nodes/validate_structure.js n8n/prompts/prompt_d_verification.md n8n/code_nodes/parse_verification.js
git commit -m "feat(n8n): add content length gate + is_in_depth verification item"
```

---

### Task 3: A2 Pipeline B — Post Entity MIN_CONTENT_LENGTH (TDD)

**Files:**
- Modify: `src/domain/entities/post.py` (add MIN_CONTENT_LENGTH to is_publishable)
- Modify: `tests/unit/domain/test_post_entity.py` (add 2 tests)
- Modify: `tests/unit/application/test_publish_posts_usecase.py` (update fixtures)
- Modify: `tests/unit/domain/test_publish_policy.py` (update fixtures)

- [ ] **Step 1: Write failing tests in test_post_entity.py**

Add to `TestIsPublishable` class:

```python
def test_false_when_content_too_short(self):
    short_body = "x" * 2999  # Just under 3000
    content = PostContent(title="Title", body_markdown=short_body)
    post = Post(row_index=1, keyword="test", content=content, quality_score=80)
    assert post.is_publishable() is False

def test_true_when_content_sufficient_length(self):
    long_body = "x" * 3000  # Exactly 3000
    content = PostContent(title="Title", body_markdown=long_body)
    post = Post(row_index=1, keyword="test", content=content, quality_score=80)
    assert post.is_publishable() is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd blog-automation && python3 -m pytest tests/unit/domain/test_post_entity.py::TestIsPublishable -v
```

Expected: 2 new tests FAIL (short content currently passes is_publishable).

- [ ] **Step 3: Implement MIN_CONTENT_LENGTH in post.py**

Update `is_publishable()` method:

```python
MIN_CONTENT_LENGTH = 3000

def is_publishable(self) -> bool:
    """True only when PENDING + quality body + sufficient length + quality_score."""
    return (
        self.status == PostStatus.PENDING
        and self.content is not None
        and self.content.has_body()
        and len(self.content.body_markdown) >= MIN_CONTENT_LENGTH
        and self.quality_score >= 70
    )
```

Define `MIN_CONTENT_LENGTH = 3000` as a module-level constant (above the Post class).

- [ ] **Step 4: Update existing test fixtures**

Existing tests that create publishable posts with short body_markdown will break. Update these fixtures to use body_markdown of 3000+ chars:

In `test_post_entity.py`:
- `test_true_when_pending_with_body`: change `body_markdown="본문 있음"` → `body_markdown="x" * 3000`
- `test_true_when_quality_score_at_least_70`: change `body_markdown="본문 있음"` → `body_markdown="x" * 3000`

In `test_publish_posts_usecase.py`:
- `make_publishable_post()` helper: change `body_markdown="## 내용\n본문"` → `body_markdown="## 내용\n" + "본문 " * 600` (3000+ chars)

In `test_publish_policy.py`:
- `_make_publishable_post()` helper: change `body_markdown="Body content"` → `body_markdown="x" * 3000`

In `test_publish_posts_usecase.py` `TestRelatedLinks` and `TestHubSpokeLinks`:
- All inline `PostContent(title=..., body_markdown="## AD\n본문")` and similar short bodies → use 3000+ char body

- [ ] **Step 5: Run all unit tests**

```bash
cd blog-automation && python3 -m pytest tests/unit/ -v
```

Expected: ALL tests PASS.

- [ ] **Step 6: Run quality checks**

```bash
cd blog-automation && python3 -m ruff check src/ tests/ && python3 -m mypy src/ --ignore-missing-imports
```

Expected: 0 warnings, 0 errors.

- [ ] **Step 7: Commit**

```bash
git add src/domain/entities/post.py tests/unit/domain/test_post_entity.py tests/unit/application/test_publish_posts_usecase.py tests/unit/domain/test_publish_policy.py
git commit -m "feat(domain): add MIN_CONTENT_LENGTH 3000 gate to is_publishable"
```

---

### Task 4: A3 — Duplicate Detection Code Node

**Files:**
- Create: `n8n/code_nodes/check_duplicate.js`

- [ ] **Step 1: Create check_duplicate.js**

```javascript
/**
 * Check Duplicate — 기존 발행글과 키워드 유사도 비교
 * Mode: runOnceForEachItem
 * 콘텐츠 생성 후, Haiku 검증 전에 배치
 * 입력: 생성된 콘텐츠 + 기존 키워드 목록 (Sheets에서 조회)
 * 출력: 중복 여부 판정
 */

const newKeyword = $input.item.json.keyword || '';

// Google Sheets에서 가져온 기존 키워드 목록 (이전 노드에서 조회)
const existingKeywords = $input.item.json.existing_keywords || [];

const OVERLAP_THRESHOLD = 0.7;

function keywordOverlap(kwA, kwB) {
  const tokensA = new Set(kwA.toLowerCase().split(/\s+/).filter(t => t.length > 0));
  const tokensB = new Set(kwB.toLowerCase().split(/\s+/).filter(t => t.length > 0));
  if (tokensA.size < 2 || tokensB.size < 2) return 0;
  const intersection = [...tokensA].filter(t => tokensB.has(t));
  const smaller = Math.min(tokensA.size, tokensB.size);
  return smaller > 0 ? intersection.length / smaller : 0;
}

let isDuplicate = false;
let duplicateOf = '';
let maxOverlap = 0;

for (const existing of existingKeywords) {
  const overlap = keywordOverlap(newKeyword, existing);
  if (overlap > maxOverlap) {
    maxOverlap = overlap;
    duplicateOf = existing;
  }
  if (overlap >= OVERLAP_THRESHOLD) {
    isDuplicate = true;
    break;
  }
}

return {
  json: {
    ...$input.item.json,
    duplicate_check: {
      is_duplicate: isDuplicate,
      duplicate_of: isDuplicate ? duplicateOf : '',
      max_overlap: Math.round(maxOverlap * 100) / 100,
      threshold: OVERLAP_THRESHOLD,
    }
  }
};
```

- [ ] **Step 2: Verify syntax**

```bash
node -c n8n/code_nodes/check_duplicate.js
```

Expected: No syntax errors.

- [ ] **Step 3: Commit**

```bash
git add n8n/code_nodes/check_duplicate.js
git commit -m "feat(n8n): add keyword-based duplicate detection code node"
```

---

### Task 5: Migration Script for Short Posts

**Files:**
- Create: `scripts/migrate_short_posts.py`

- [ ] **Step 1: Create migration script**

```python
"""Migrate short pending posts to '검수필요' status.

Finds all '발행대기' posts with body < 3000 chars and marks them '검수필요'.
Run once after deploying MIN_CONTENT_LENGTH gate.

Usage:
    python scripts/migrate_short_posts.py --dry-run
    python scripts/migrate_short_posts.py
"""
from __future__ import annotations

import argparse
import json
import sys

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
MIN_CONTENT_LENGTH = 3000
COL_STATUS = 3       # C열
COL_CONTENT = 15     # O열
COL_ERROR_MSG = 13   # M열


def main():
    parser = argparse.ArgumentParser(description="Migrate short posts to 검수필요")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change")
    parser.add_argument("--creds", default="credentials.json", help="Google credentials path")
    parser.add_argument("--sheet", default="blog-automation", help="Sheet name")
    args = parser.parse_args()

    creds = Credentials.from_service_account_file(args.creds, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open(args.sheet).sheet1

    all_rows = sheet.get_all_values()
    targets = []

    for i, row in enumerate(all_rows[1:], start=2):  # skip header
        status = row[COL_STATUS - 1] if len(row) >= COL_STATUS else ""
        content = row[COL_CONTENT - 1] if len(row) >= COL_CONTENT else ""
        keyword = row[0] if len(row) >= 1 else ""

        if status == "발행대기" and len(content) < MIN_CONTENT_LENGTH:
            targets.append((i, keyword, len(content)))

    if not targets:
        print("No short posts found. Nothing to migrate.")
        return

    print(f"Found {len(targets)} short posts:")
    for row_idx, kw, length in targets:
        print(f"  Row {row_idx}: {kw} ({length} chars)")

    if args.dry_run:
        print("\n--dry-run mode. No changes made.")
        return

    confirm = input(f"\nUpdate {len(targets)} posts to '검수필요'? [y/N] ")
    if confirm.lower() != "y":
        print("Aborted.")
        return

    from gspread import Cell
    cells = []
    for row_idx, kw, length in targets:
        cells.append(Cell(row=row_idx, col=COL_STATUS, value="검수필요"))
        cells.append(Cell(row=row_idx, col=COL_ERROR_MSG,
                          value=f"본문 {MIN_CONTENT_LENGTH}자 미만 ({length}자) - 자동 전환"))

    sheet.update_cells(cells)
    print(f"Updated {len(targets)} posts to '검수필요'.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('scripts/migrate_short_posts.py').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate_short_posts.py
git commit -m "feat: add migration script for short posts → 검수필요"
```

---

## Chunk 2: Prompt Enhancement

### Task 6: Enhance prompt_a_terminology.md

**Files:**
- Modify: `n8n/prompts/prompt_a_terminology.md`

Rewrite to require 3000+ chars minimum, with these E-E-A-T enhanced sections:

- [ ] **Step 1: Rewrite prompt_a_terminology.md**

Key changes from current version:
1. **분량**: "최소 1,500자" → "최소 3,000자 이상 (마크다운 기준, 4,000자 권장)"
2. **필수 섹션 추가/확장**:
   - "왜 중요한지 (Why)" — 실무 시나리오 2개 이상 (신규)
   - "실무 적용 가이드" — 구체적 도구명, 설정값, 명령어 (신규)
   - 기존 "작동 원리" → 3~5단계 + 각 단계 기술적 세부사항 (확장)
   - 기존 "장점과 한계" → 비교표 or 체크리스트 1개 이상 필수 (확장)
3. **품질 체크리스트 강화**:
   - "전체 본문이 3,000자 이상인가?" (1500 → 3000)
   - "실무 시나리오가 2개 이상인가?" (신규)
   - "실무 적용 가이드에 구체적 도구/명령어가 있는가?" (신규)
4. **SERP 활용 강화**:
   - "SERP 상위 결과를 참고하되 그대로 복사하지 말 것"
   - "인라인 출처: 유용한 정보는 '[출처명](URL)' 형태로 삽입"
5. **금지사항 수정**:
   - `contoso.com` 의무 사용 → "가상 도메인 대신 설명 텍스트 사용"
6. **JSON 출력**: `content` 필드 최소 글자 수: "최소 3000자 이상"

**Keep unchanged**: Mermaid diagram rules, IMAGE marker rules, code example rules, JSON output format structure, internal_link_keywords bolding rule.

- [ ] **Step 2: Verify markdown renders correctly**

Visually inspect the file for broken formatting.

- [ ] **Step 3: Commit**

```bash
git add n8n/prompts/prompt_a_terminology.md
git commit -m "feat(n8n): enhance prompt A for 3000+ chars with E-E-A-T sections"
```

---

### Task 7: Enhance prompt_b_comparison.md

**Files:**
- Modify: `n8n/prompts/prompt_b_comparison.md`

- [ ] **Step 1: Rewrite prompt_b_comparison.md**

Key changes from current version:
1. **분량**: "최소 2,000자" → "최소 3,000자 이상 (마크다운 기준, 4,500자 권장)"
2. **필수 섹션 추가/확장**:
   - "핵심 차이 요약 비교표" — 글 상단에 위치 (강화)
   - "각 항목별 심층 비교" — 기능, 성능, 비용, 사용성 분리 (확장)
   - "실제 선택 기준" — "A를 선택해야 할 때 vs B를 선택해야 할 때" (확장)
   - "실무 마이그레이션/도입 시나리오" (신규)
3. **품질 체크리스트 강화**:
   - "전체 본문이 3,000자 이상인가?" (2000 → 3000)
   - "마이그레이션/도입 시나리오가 포함되어 있는가?" (신규)
4. **SERP 활용 강화**: 인라인 출처 삽입 지시 추가
5. **금지사항 수정**: `contoso.com` → 설명 텍스트 사용

- [ ] **Step 2: Verify markdown**
- [ ] **Step 3: Commit**

```bash
git add n8n/prompts/prompt_b_comparison.md
git commit -m "feat(n8n): enhance prompt B for 3000+ chars with deep comparison"
```

---

### Task 8: Enhance prompt_c_troubleshooting.md

**Files:**
- Modify: `n8n/prompts/prompt_c_troubleshooting.md`

- [ ] **Step 1: Rewrite prompt_c_troubleshooting.md**

Key changes from current version:
1. **분량**: "최소 2,000자" → "최소 3,000자 이상 (마크다운 기준, 5,000자 권장)"
2. **필수 섹션 추가/확장**:
   - "에러 메시지 원문" — 영문 + 한글 설명 (확장)
   - "원인 분석" — 3가지 이상 가능한 원인 (기존 유지)
   - "단계별 해결 방법" — 코드 블록/명령어 포함 (확장: 각 해결법에 실행 전 확인 + 실행 후 확인 명령어)
   - "예방 방법" (기존 유지)
   - "관련 에러 링크" (신규)
3. **품질 체크리스트 강화**:
   - "전체 본문이 3,000자 이상인가?" (2000 → 3000)
   - "관련 에러 링크가 포함되어 있는가?" (신규)
4. **SERP 활용 강화**: 인라인 출처 삽입 지시 추가
5. **금지사항 수정**: `contoso.com` → 설명 텍스트 사용

- [ ] **Step 2: Verify markdown**
- [ ] **Step 3: Commit**

```bash
git add n8n/prompts/prompt_c_troubleshooting.md
git commit -m "feat(n8n): enhance prompt C for 3000+ chars with structured troubleshooting"
```

---

## Chunk 3: Workflow Sync

### Task 9: Sync workflow_complete.json

**Files:**
- Modify: `n8n/workflow_complete.json`

This is a large JSON file containing embedded JS code in `jsCode` fields. Two existing nodes need code updates, and one new node needs to be wired in.

- [ ] **Step 1: Update validate_structure node's jsCode**

Find the node named "Validate Structure" in the JSON and replace its `jsCode` field with the updated content from `n8n/code_nodes/validate_structure.js`. The JS code must be JSON-escaped (newlines as `\n`, quotes as `\"`).

- [ ] **Step 2: Update parse_verification node's jsCode**

Find the node named containing "Parse" and "Verification" (or similar) and replace its `jsCode` with the updated `n8n/code_nodes/parse_verification.js` content.

- [ ] **Step 3: Note about check_duplicate node**

The check_duplicate.js node needs to be added to the workflow. However, wiring n8n nodes requires UI-level connection changes (node positions, connections array). Document this as a manual step: "Import check_duplicate.js code into a new Code node in n8n UI, position between content generation and Haiku verification."

- [ ] **Step 4: Commit**

```bash
git add n8n/workflow_complete.json
git commit -m "feat(n8n): sync workflow JSON with updated code nodes"
```
