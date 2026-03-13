# tistory_editor.py Module Split Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 1,892-line `tistory_editor.py` into 7 focused modules (6 new + 1 shrunk orchestrator) and remove 243 LOC of deprecated code.

**Architecture:** Pure structural refactoring — extract functions into new modules by responsibility, update imports in the orchestrator and all external callers, delete deprecated functions. Zero behavioral changes.

**Tech Stack:** Python 3.9+, SeleniumBase, markdown library

**Spec:** `docs/superpowers/specs/2026-03-12-tistory-editor-split-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/infrastructure/browser/markdown_converter.py` | Create | MD→HTML conversion + Mermaid handling |
| `src/infrastructure/browser/html_transformer.py` | Create | HTML post-processing + validation |
| `src/infrastructure/browser/form_filler.py` | Create | DOM form field interaction |
| `src/infrastructure/browser/content_injector.py` | Create | WYSIWYG editor HTML injection |
| `src/infrastructure/browser/api_publisher.py` | Create | Tistory API call (`call_tistory_post_api`) + React state fallback (`try_publish_via_react_state`) |
| `src/infrastructure/browser/publish_verifier.py` | Create | Post-publish verification + visibility fix |
| `src/infrastructure/browser/tistory_editor.py` | Shrink | Orchestrator only (publish_post, update_post) |
| `src/infrastructure/browser/adsense_pages.py` | Modify | Import fix |
| `tests/unit/infrastructure/test_markdown_to_html.py` | Modify | Import fix |

---

## Chunk 1: Extract Pure Modules (no Selenium dependency)

### Task 1: Create `markdown_converter.py`

Extract Markdown-to-HTML conversion functions.

**Files:**
- Create: `src/infrastructure/browser/markdown_converter.py`
- Reference: `src/infrastructure/browser/tistory_editor.py:1136-1253`

- [ ] **Step 1: Create `markdown_converter.py` with all 4 functions**

Copy these functions from `tistory_editor.py` into the new file. Rename `_style_mermaid_fallback` to `style_mermaid_fallback` (public, directly tested). Keep other internal functions with underscore prefix.

```python
"""markdown_converter — Markdown to HTML conversion with Mermaid support."""
from __future__ import annotations

import logging
import re

import markdown as md_lib

logger = logging.getLogger(__name__)
```

Functions to copy (preserve exact implementation, only change function name for `style_mermaid_fallback`):
- `_render_mermaid_via_kroki` (lines 1136-1156) — keep as `_render_mermaid_via_kroki`
- `_preserve_mermaid_blocks` (lines 1159-1201) — keep as `_preserve_mermaid_blocks`
- `convert_markdown_to_html` (lines 1203-1237) — keep as `convert_markdown_to_html`
- `_style_mermaid_fallback` (lines 1239-1253) — rename to `style_mermaid_fallback`

- [ ] **Step 2: Verify the module imports correctly**

Run: `python -c "from src.infrastructure.browser.markdown_converter import convert_markdown_to_html, style_mermaid_fallback; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Run existing tests to verify no breakage (tests still import from tistory_editor)**

Run: `python -m pytest tests/unit/infrastructure/test_markdown_to_html.py -v`
Expected: All tests PASS (tistory_editor.py still has the old functions at this point)

- [ ] **Step 4: Commit**

```bash
git add src/infrastructure/browser/markdown_converter.py
git commit -m "refactor(infra): extract markdown_converter module from tistory_editor"
```

---

### Task 2: Create `html_transformer.py`

Extract HTML post-processing and validation functions.

**Files:**
- Create: `src/infrastructure/browser/html_transformer.py`
- Reference: `src/infrastructure/browser/tistory_editor.py:80-83,1256-1325,1832-1839`

- [ ] **Step 1: Create `html_transformer.py` with all 5 functions**

```python
"""html_transformer — HTML post-processing: lazy loading, nofollow, FAQ schema, validation."""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)
```

Functions to copy (drop leading underscore where noted):
- `_extract_first_image_url` (lines 80-83) → `extract_first_image_url` — contains lazy import of `ThumbnailService`
- `_add_lazy_loading` (lines 1256-1270) → `add_lazy_loading` — includes inner `_replace_img` closure
- `_add_nofollow_to_external_links` (lines 1273-1305) → `add_nofollow_to_external_links` — includes inner `_process_anchor` closure
- `validate_html` (lines 1308-1325) → `validate_html` — stays public, contains lazy import of `HtmlValidationService`
- `_append_faq_schema` (lines 1832-1839) → `append_faq_schema`

- [ ] **Step 2: Verify the module imports correctly**

Run: `python -c "from src.infrastructure.browser.html_transformer import add_lazy_loading, validate_html; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Run existing tests**

Run: `python -m pytest tests/unit/infrastructure/test_markdown_to_html.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/infrastructure/browser/html_transformer.py
git commit -m "refactor(infra): extract html_transformer module from tistory_editor"
```

---

## Chunk 2: Extract Selenium-Dependent Modules

### Task 3: Create `form_filler.py`

Extract DOM form interaction functions.

**Files:**
- Create: `src/infrastructure/browser/form_filler.py`
- Reference: `src/infrastructure/browser/tistory_editor.py:86-161,770-804,1453-1546,1693-1765`

- [ ] **Step 1: Create `form_filler.py` with all 6 functions**

```python
"""form_filler — DOM interaction for Tistory editor form fields."""
from __future__ import annotations

import logging
import re
import time

from src.infrastructure.browser.dom_selectors import (
    PUBLISH_CONFIRM_SELECTORS,
    TAG_INPUT_SELECTORS,
    find_element,
)

logger = logging.getLogger(__name__)
```

Functions to copy (drop leading underscore):
- `_safe_click` (lines 86-124) → `safe_click`
- `_safe_type` (lines 127-161) → `safe_type`
- `_select_category_in_layer` (lines 770-804) → `select_category_in_layer`
- `_select_public_mode` (lines 1453-1546) → `select_public_mode`
- `_input_tags` (lines 1693-1731) → `input_tags`
- `_inject_meta_description` (lines 1732-1765) → `inject_meta_description`

**Important:** Check each function for `dom_selectors` imports needed. Only import the constants actually used. Specifically:
- `safe_click` and `safe_type` don't use dom_selectors directly
- `select_public_mode` uses `PUBLISH_CONFIRM_SELECTORS` and `find_element`
- `input_tags` uses `TAG_INPUT_SELECTORS` and `find_element`
- `inject_meta_description` uses `find_element`

Adjust the imports at the top of the file to include only what's needed.

- [ ] **Step 2: Verify the module imports correctly**

Run: `python -c "from src.infrastructure.browser.form_filler import safe_click, safe_type, input_tags; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/infrastructure/browser/form_filler.py
git commit -m "refactor(infra): extract form_filler module from tistory_editor"
```

---

### Task 4: Create `content_injector.py`

Extract WYSIWYG editor content injection functions.

**Files:**
- Create: `src/infrastructure/browser/content_injector.py`
- Reference: `src/infrastructure/browser/tistory_editor.py:1328-1451,1767-1810,1842-1892`

- [ ] **Step 1: Create `content_injector.py` with all 4 functions**

```python
"""content_injector — HTML content injection into Tistory WYSIWYG editor."""
from __future__ import annotations

import logging
import time

from src.infrastructure.browser.dom_selectors import (
    CONTENT_AREA_SELECTORS,
    TINYMCE_IFRAME_SELECTORS,
    find_element,
)

logger = logging.getLogger(__name__)
```

Functions to copy (drop leading underscore):
- `_wait_for_wysiwyg_editor` (lines 1328-1351) → `wait_for_wysiwyg_editor`
- `_inject_html_content` (lines 1352-1451) → `inject_html_content`
- `_install_ajax_content_interceptor` (lines 1767-1810) → `install_ajax_content_interceptor`
- `_ensure_content_in_form` (lines 1842-1892) → `ensure_content_in_form`

**Important:** Check which `dom_selectors` constants each function uses:
- `wait_for_wysiwyg_editor` uses `TINYMCE_IFRAME_SELECTORS`, `find_element`
- `inject_html_content` uses `CONTENT_AREA_SELECTORS`, `TINYMCE_IFRAME_SELECTORS`, `find_element`
- `ensure_content_in_form` uses `CONTENT_AREA_SELECTORS`, `find_element`
- `install_ajax_content_interceptor` doesn't use dom_selectors

- [ ] **Step 2: Verify the module imports correctly**

Run: `python -c "from src.infrastructure.browser.content_injector import inject_html_content, wait_for_wysiwyg_editor; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/infrastructure/browser/content_injector.py
git commit -m "refactor(infra): extract content_injector module from tistory_editor"
```

---

### Task 5: Create `publish_verifier.py`

Extract post-publication verification functions.

**Files:**
- Create: `src/infrastructure/browser/publish_verifier.py`
- Reference: `src/infrastructure/browser/tistory_editor.py:164-194,805-887,1547-1606,1812-1831`

- [ ] **Step 1: Create `publish_verifier.py` with all 7 functions**

```python
"""publish_verifier — Post-publication verification, URL extraction, visibility fixing."""
from __future__ import annotations

import logging
import re
import time

from src.infrastructure.browser import form_filler

logger = logging.getLogger(__name__)
```

Functions to copy (drop leading underscore):
- `_check_publish_layer_opened` (lines 164-193) → `check_publish_layer_opened`
- `_click_publish_confirm_in_modal` (lines 805-887) → `click_publish_confirm_in_modal`
  - **Important:** This function contains an inner function `_after_publish`. Keep it as-is inside the outer function.
  - **Important:** This function calls `_safe_click`. Change to `form_filler.safe_click`.
  - **Important:** This function calls `_extract_published_url`. Change to `extract_published_url` (same module).
- `_extract_published_url` (lines 1547-1572) → `extract_published_url`
- `_verify_published_url` (lines 1574-1597) → `verify_published_url`
- `_extract_post_id` (lines 1600-1603) → `extract_post_id`
- `_fix_post_visibility` (lines 1606-1691) → `fix_post_visibility`
  - **Important:** This function calls `_safe_click`. Change to `form_filler.safe_click`.
- `_verify_faq_schema` (lines 1812-1831) → `verify_faq_schema`

- [ ] **Step 2: Verify the module imports correctly**

Run: `python -c "from src.infrastructure.browser.publish_verifier import verify_published_url, extract_post_id; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/infrastructure/browser/publish_verifier.py
git commit -m "refactor(infra): extract publish_verifier module from tistory_editor"
```

---

### Task 6: Create `api_publisher.py`

Extract Tistory API publishing functions.

**Files:**
- Create: `src/infrastructure/browser/api_publisher.py`
- Reference: `src/infrastructure/browser/tistory_editor.py:464-767`

- [ ] **Step 1: Create `api_publisher.py` with all 3 functions**

```python
"""api_publisher — Tistory API (XHR) and React Redux state publishing."""
from __future__ import annotations

import logging
import re
import time

from src.domain.exceptions import DailyPublishLimitError
from src.infrastructure.browser import form_filler
from src.infrastructure.browser import publish_verifier

logger = logging.getLogger(__name__)

_DAILY_LIMIT_PATTERN = "최대 15개까지"
```

Functions to copy (drop leading underscore):
- `_call_tistory_post_api` (lines 500-639) → `call_tistory_post_api`
  - Contains `import json as json_mod` inline — keep as-is
- `_try_publish_via_react_state` (lines 641-767) → `try_publish_via_react_state`
  - **Important:** Change internal calls:
    - `_check_publish_layer_opened(sb)` → `publish_verifier.check_publish_layer_opened(sb)`
    - `_select_public_mode(sb)` → `form_filler.select_public_mode(sb)`
    - `_select_category_in_layer(sb, category_id)` → `form_filler.select_category_in_layer(sb, category_id)`
    - `_click_publish_confirm_in_modal(sb, blog_name)` → `publish_verifier.click_publish_confirm_in_modal(sb, blog_name)`
  - Contains `import json as json_mod` inline — keep as-is
- `_publish_via_api` (lines 464-497) → `publish_via_api`
  - **Important:** This function calls `_extract_first_image_url` and `_resolve_category_id`. These stay in the orchestrator (`tistory_editor.py`), so this function must NOT be a simple copy — see note below.

**CRITICAL NOTE on `publish_via_api`:** This function currently calls `_extract_first_image_url` and `_resolve_category_id`. Since those responsibilities belong to other modules (`html_transformer` and the orchestrator respectively), `publish_via_api` should be refactored to receive the resolved values as parameters instead of calling these functions directly. Alternatively, it can stay in the orchestrator. **Decision: Keep `_publish_via_api` in the orchestrator** (`tistory_editor.py`) since it calls `_extract_first_image_url` (→ `html_transformer`) and `_resolve_category_id` (orchestrator) — moving it would create unnecessary coupling. Only move `call_tistory_post_api` and `try_publish_via_react_state` to `api_publisher.py`.

Revised function list for `api_publisher.py`:
- `call_tistory_post_api` (lines 500-639)
- `try_publish_via_react_state` (lines 641-767)

`publish_via_api` stays in the orchestrator.

- [ ] **Step 2: Verify the module imports correctly**

Run: `python -c "from src.infrastructure.browser.api_publisher import call_tistory_post_api, try_publish_via_react_state; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/infrastructure/browser/api_publisher.py
git commit -m "refactor(infra): extract api_publisher module from tistory_editor"
```

---

## Chunk 3: Rewire Orchestrator and Callers

### Task 7: Shrink `tistory_editor.py` to orchestrator

Remove all extracted functions, add submodule imports, update internal calls.

**Files:**
- Modify: `src/infrastructure/browser/tistory_editor.py`

- [ ] **Step 1: Update imports at top of file**

Replace the import block. Remove `markdown as md_lib` (moved to markdown_converter). Remove unused `dom_selectors` imports (only keep what orchestrator itself uses). Add submodule imports:

```python
from src.infrastructure.browser import markdown_converter
from src.infrastructure.browser import html_transformer
from src.infrastructure.browser import form_filler
from src.infrastructure.browser import content_injector
from src.infrastructure.browser import api_publisher
from src.infrastructure.browser import publish_verifier
```

Keep existing imports that the orchestrator still needs:
- `from src.domain.entities.post import Post`
- `from src.domain.value_objects.publish_result import PublishResult`
- `from src.domain.value_objects.site_profile import CategoryMapping, SiteProfile`
- `from src.infrastructure.browser.dom_selectors import EDITOR_PATH, TITLE_SELECTORS, find_element`
- `from src.infrastructure.seo.html_optimizer import optimize_html`

- [ ] **Step 2: Delete extracted functions from `tistory_editor.py`**

Delete these function definitions (they now live in submodules):
- `_extract_first_image_url` (lines 80-83)
- `_safe_click` (lines 86-124)
- `_safe_type` (lines 127-161)
- `_check_publish_layer_opened` (lines 164-193)
- `_call_tistory_post_api` (lines 500-639)
- `_try_publish_via_react_state` (lines 641-767)
- `_select_category_in_layer` (lines 770-804)
- `_click_publish_confirm_in_modal` (lines 805-887)
- `_render_mermaid_via_kroki` (lines 1136-1156)
- `_preserve_mermaid_blocks` (lines 1159-1201)
- `convert_markdown_to_html` (lines 1203-1237)
- `_style_mermaid_fallback` (lines 1239-1253)
- `_add_lazy_loading` (lines 1256-1270)
- `_add_nofollow_to_external_links` (lines 1273-1305)
- `validate_html` (lines 1308-1325)
- `_wait_for_wysiwyg_editor` (lines 1328-1351)
- `_inject_html_content` (lines 1352-1451)
- `_select_public_mode` (lines 1453-1546)
- `_extract_published_url` (lines 1547-1572)
- `_verify_published_url` (lines 1574-1597)
- `_extract_post_id` (lines 1600-1603)
- `_fix_post_visibility` (lines 1606-1691)
- `_input_tags` (lines 1693-1731)
- `_inject_meta_description` (lines 1732-1765)
- `_install_ajax_content_interceptor` (lines 1767-1810)
- `_verify_faq_schema` (lines 1812-1831)
- `_append_faq_schema` (lines 1832-1839)
- `_ensure_content_in_form` (lines 1842-1892)

- [ ] **Step 3: Delete deprecated functions**

Delete these unused functions:
- `_switch_to_markdown_mode` (lines 889-995, 105 LOC)
- `_inject_markdown_content` (lines 996-1135, 138 LOC)

- [ ] **Step 4: Update `publish_post()` internal calls**

Replace all direct function calls in `publish_post()` with module-qualified calls:

| Old call | New call |
|----------|----------|
| `convert_markdown_to_html(body_markdown)` | `markdown_converter.convert_markdown_to_html(body_markdown)` |
| `_add_lazy_loading(html_body)` | `html_transformer.add_lazy_loading(html_body)` |
| `_add_nofollow_to_external_links(html_body, blog_name)` | `html_transformer.add_nofollow_to_external_links(html_body, blog_name)` |
| `validate_html(html_body)` | `html_transformer.validate_html(html_body)` |
| `_append_faq_schema(html_body, faq_ld_json)` | `html_transformer.append_faq_schema(html_body, faq_ld_json)` |
| `_wait_for_wysiwyg_editor(sb)` | `content_injector.wait_for_wysiwyg_editor(sb)` |
| `_install_ajax_content_interceptor(sb, html_body)` | `content_injector.install_ajax_content_interceptor(sb, html_body)` |
| `_inject_html_content(sb, html_body)` | `content_injector.inject_html_content(sb, html_body)` |
| `_input_tags(sb, content.tag_list())` | `form_filler.input_tags(sb, content.tag_list())` |
| `_inject_meta_description(sb, content.meta_description)` | `form_filler.inject_meta_description(sb, content.meta_description)` |
| `_ensure_content_in_form(sb, html_body)` | `content_injector.ensure_content_in_form(sb, html_body)` |
| `_safe_click(sb, title_sel)` | `form_filler.safe_click(sb, title_sel)` |
| `_safe_type(sb, title_sel, title_text)` | `form_filler.safe_type(sb, title_sel, title_text)` |
| `_verify_published_url(published_url)` | `publish_verifier.verify_published_url(published_url)` |
| `_verify_faq_schema(published_url)` | `publish_verifier.verify_faq_schema(published_url)` |
| `_fix_post_visibility(sb, blog_name, published_url)` | `publish_verifier.fix_post_visibility(sb, blog_name, published_url)` |

**Note:** `_publish_via_api` stays in the orchestrator. Update its internal calls:
- `_extract_first_image_url(html_body)` → `html_transformer.extract_first_image_url(html_body)`
- `_call_tistory_post_api(...)` → `api_publisher.call_tistory_post_api(...)`
- `_try_publish_via_react_state(...)` → `api_publisher.try_publish_via_react_state(...)`

- [ ] **Step 5: Update `update_post()` internal calls**

`update_post()` uses the API-only path (no WYSIWYG editor, no form filling). Replace:

| Old call | New call |
|----------|----------|
| `convert_markdown_to_html(body_markdown)` | `markdown_converter.convert_markdown_to_html(body_markdown)` |
| `_add_lazy_loading(html_body)` | `html_transformer.add_lazy_loading(html_body)` |
| `_add_nofollow_to_external_links(html_body, blog_name)` | `html_transformer.add_nofollow_to_external_links(html_body, blog_name)` |
| `_append_faq_schema(html_body, faq_ld_json)` | `html_transformer.append_faq_schema(html_body, faq_ld_json)` |
| `_extract_first_image_url(html_body)` | `html_transformer.extract_first_image_url(html_body)` |
| `_call_tistory_post_api(...)` | `api_publisher.call_tistory_post_api(...)` |
| `_verify_published_url(published_url)` | `publish_verifier.verify_published_url(published_url)` |
| `_fix_post_visibility(sb, ...)` | `publish_verifier.fix_post_visibility(sb, ...)` |

**Note:** `update_post()` does NOT call `_wait_for_wysiwyg_editor`, `_inject_html_content`, `_ensure_content_in_form`, `_safe_click`, `_safe_type`, `_input_tags`, or `_inject_meta_description` — it uses the API-only path without WYSIWYG form interaction.

- [ ] **Step 6: Verify orchestrator has no remaining references to deleted functions**

Run: `grep -n "def _safe_click\|def _safe_type\|def convert_markdown\|def _add_lazy\|def _add_nofollow\|def validate_html\|def _inject_html\|def _wait_for_wysiwyg\|def _select_public\|def _select_category\|def _input_tags\|def _inject_meta\|def _ensure_content\|def _install_ajax\|def _call_tistory\|def _try_publish\|def _publish_via_api\|def _check_publish\|def _click_publish\|def _extract_published\|def _verify_published\|def _extract_post_id\|def _fix_post\|def _verify_faq\|def _append_faq\|def _extract_first\|def _render_mermaid\|def _preserve_mermaid\|def _style_mermaid\|def _switch_to_markdown\|def _inject_markdown" src/infrastructure/browser/tistory_editor.py`

Expected: Only `def _publish_via_api` should remain (if kept in orchestrator). No other extracted function definitions.

- [ ] **Step 7: Run lint and typecheck**

Run: `make lint && make typecheck`
Expected: 0 warnings, 0 errors

- [ ] **Step 8: Commit**

```bash
git add src/infrastructure/browser/tistory_editor.py
git commit -m "refactor(infra): shrink tistory_editor to orchestrator — delegate to submodules"
```

---

### Task 8: Update external callers

Fix imports in `adsense_pages.py` and `test_markdown_to_html.py`.

**Files:**
- Modify: `src/infrastructure/browser/adsense_pages.py:10`
- Modify: `tests/unit/infrastructure/test_markdown_to_html.py:1-11`

- [ ] **Step 1: Update `adsense_pages.py` import**

Change line 10:
```python
# Before:
from src.infrastructure.browser.tistory_editor import _call_tistory_post_api
# After:
from src.infrastructure.browser.api_publisher import call_tistory_post_api
```

Then find-and-replace all calls in the file:
- `_call_tistory_post_api(` → `call_tistory_post_api(`

- [ ] **Step 2: Update `test_markdown_to_html.py` imports**

Replace the import block at lines 1-11:
```python
# Before:
from src.infrastructure.browser.tistory_editor import (
    _add_lazy_loading,
    _add_nofollow_to_external_links,
    _extract_post_id,
    _style_mermaid_fallback,
    _verify_faq_schema,
    _verify_published_url,
    convert_markdown_to_html,
    validate_html,
)

# After:
from src.infrastructure.browser.markdown_converter import (
    convert_markdown_to_html,
    style_mermaid_fallback,
)
from src.infrastructure.browser.html_transformer import (
    add_lazy_loading,
    add_nofollow_to_external_links,
    validate_html,
)
from src.infrastructure.browser.publish_verifier import (
    extract_post_id,
    verify_faq_schema,
    verify_published_url,
)
```

Then update all function references in the test file:
- `_add_lazy_loading(` → `add_lazy_loading(`
- `_add_nofollow_to_external_links(` → `add_nofollow_to_external_links(`
- `_extract_post_id(` → `extract_post_id(`
- `_style_mermaid_fallback(` → `style_mermaid_fallback(`
- `_verify_faq_schema(` → `verify_faq_schema(`
- `_verify_published_url(` → `verify_published_url(`

- [ ] **Step 3: Run all unit tests**

Run: `make test-unit`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/infrastructure/browser/adsense_pages.py tests/unit/infrastructure/test_markdown_to_html.py
git commit -m "refactor(infra): update external callers for tistory_editor split"
```

---

## Chunk 4: Final Verification

### Task 9: Full quality gate

Run the complete quality gate suite.

**Files:** None (verification only)

- [ ] **Step 1: Run all unit tests**

Run: `make test-unit`
Expected: All tests PASS

- [ ] **Step 2: Run lint**

Run: `make lint`
Expected: 0 warnings

- [ ] **Step 3: Run typecheck**

Run: `make typecheck`
Expected: `Success: no issues found in N source files`

- [ ] **Step 4: Run DDD validation**

Run: `make validate-ddd`
Expected: 0 violations (all new modules are in `src/infrastructure/browser/`)

- [ ] **Step 5: Verify file structure**

Run: `ls -la src/infrastructure/browser/markdown_converter.py src/infrastructure/browser/html_transformer.py src/infrastructure/browser/form_filler.py src/infrastructure/browser/content_injector.py src/infrastructure/browser/api_publisher.py src/infrastructure/browser/publish_verifier.py`
Expected: All 6 files exist

- [ ] **Step 6: Verify orchestrator LOC reduction**

Run: `wc -l src/infrastructure/browser/tistory_editor.py`
Expected: ~290 lines (down from 1,892)

- [ ] **Step 7: Verify deprecated functions removed**

Run: `grep -c "_switch_to_markdown_mode\|_inject_markdown_content" src/infrastructure/browser/tistory_editor.py`
Expected: 0 (only comments referencing the removal may exist)
