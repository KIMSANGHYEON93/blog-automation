# tistory_editor.py Module Split Design

## Problem

`src/infrastructure/browser/tistory_editor.py` is a 1,892-line monolithic module containing 36 functions spanning 7 distinct responsibilities: Markdown-to-HTML conversion, HTML optimization, form filling, content injection, API publishing, post-publication verification, and orchestration. This violates Single Responsibility Principle, makes the module difficult to navigate, test in isolation, and maintain.

## Goal

Split `tistory_editor.py` into 6 new focused modules + 1 shrunk orchestrator, following a flat module approach (no class conversion). Remove 2 deprecated functions (~243 LOC). Total LOC redistributed from ~1,892 to ~1,650 across 7 files.

## Constraints

- **Infrastructure layer only** — all new modules stay in `src/infrastructure/browser/`
- **No class conversion** — keep functions as module-level functions (procedural style)
- **No behavioral changes** — pure structural refactoring, zero logic changes
- **External caller contracts preserved** — see "Affected Callers" section for all callers and required updates
- **Remove deprecated code** — `_switch_to_markdown_mode()` (105 LOC) and `_inject_markdown_content()` (138 LOC) are unused and must be deleted

## Current Structure

**File**: `src/infrastructure/browser/tistory_editor.py` (1,892 LOC, 36 functions)

**External callers** (4 files):
- `selenium_adapter.py` — imports `publish_post`, `update_post`
- `cli.py` — imports `set_site_profile`
- `adsense_pages.py` — imports `_call_tistory_post_api`
- `tests/unit/infrastructure/test_markdown_to_html.py` — imports `convert_markdown_to_html`, `validate_html`, `_add_lazy_loading`, `_add_nofollow_to_external_links`, `_extract_post_id`, `_style_mermaid_fallback`, `_verify_faq_schema`, `_verify_published_url`

**Dependency graph of entry points**:
- `publish_post()` calls: `_get_profile`, `_resolve_category_id`, `convert_markdown_to_html`, `_add_lazy_loading`, `_add_nofollow_to_external_links`, `_append_faq_schema`, `optimize_html`, `_wait_for_wysiwyg_editor`, `_inject_html_content`, `_install_ajax_content_interceptor`, `_ensure_content_in_form`, `_safe_click`, `_safe_type`, `_input_tags`, `_inject_meta_description`, `_select_category_in_layer`, `_select_public_mode`, `_check_publish_layer_opened`, `_publish_via_api`, `_extract_published_url`, `_verify_published_url`, `_verify_faq_schema`, `_fix_post_visibility`, `_extract_post_id`
- `update_post()` calls: `_get_profile`, `convert_markdown_to_html`, `_add_lazy_loading`, `_add_nofollow_to_external_links`, `_append_faq_schema`, `optimize_html`, `_wait_for_wysiwyg_editor`, `_inject_html_content`, `_ensure_content_in_form`, `_safe_click`, `_safe_type`, `_input_tags`, `_inject_meta_description`

## Proposed Module Structure

### 1. `markdown_converter.py` (~120 LOC)

**Responsibility**: Markdown text to HTML conversion, including Mermaid diagram handling.

**Functions** (moved from tistory_editor.py):
- `convert_markdown_to_html(md_text: str) -> str` (line 1203) — public entry point
- `_preserve_mermaid_blocks(md_text: str) -> str` (line 1159) — internal
- `_render_mermaid_via_kroki(code: str) -> str | None` (line 1136) — internal
- `_style_mermaid_fallback(html_text: str) -> str` (line 1239) — internal

**Dependencies**: `markdown` (md_lib), `re`, `urllib.request` (stdlib, for Kroki API)

**No Selenium dependency** — pure transformation logic.

### 2. `html_transformer.py` (~100 LOC)

**Responsibility**: Post-conversion HTML transformations and validation (lazy loading, nofollow, FAQ schema, content validation).

**Functions**:
- `_add_lazy_loading(html_text: str) -> str` (line 1256) — renamed to `add_lazy_loading`
- `_add_nofollow_to_external_links(html_text: str, blog_name: str) -> str` (line 1273) — renamed to `add_nofollow_to_external_links`
- `_append_faq_schema(body_markdown: str, faq_ld_json: str) -> str` (line 1832) — renamed to `append_faq_schema`
- `_extract_first_image_url(html: str) -> str` (line 80) — renamed to `extract_first_image_url`
- `validate_html(html_text: str) -> bool` (line 1308) — stays public (pre-publish content validation)

**Dependencies**: `re`, `src.domain.services.thumbnail_service.ThumbnailService` (for `extract_first_image_url`), `src.domain.services.html_validation.HtmlValidationService` (for `validate_html`)

**No Selenium dependency** — pure transformation logic.

### 3. `form_filler.py` (~270 LOC)

**Responsibility**: DOM interaction for filling Tistory editor form fields (title, tags, category, meta description, visibility).

**Functions**:
- `_safe_click(sb, selector: str) -> bool` (line 86) — renamed to `safe_click`
- `_safe_type(sb, selector: str, text: str) -> bool` (line 127) — renamed to `safe_type`
- `_input_tags(sb, tags: list[str]) -> None` (line 1693)
- `_inject_meta_description(sb, meta_description: str) -> None` (line 1732)
- `_select_category_in_layer(sb, category_id: str) -> None` (line 770)
- `_select_public_mode(sb) -> None` (line 1453)

**Dependencies**: SeleniumBase (`sb` parameter), `dom_selectors`

### 4. `content_injector.py` (~215 LOC)

**Responsibility**: Injecting HTML content into the Tistory WYSIWYG editor.

**Functions**:
- `_inject_html_content(sb, html_text: str) -> bool` (line 1352) — renamed to `inject_html_content`
- `_wait_for_wysiwyg_editor(sb, timeout: int = 10) -> None` (line 1328) — renamed to `wait_for_wysiwyg_editor`
- `_ensure_content_in_form(sb, html_text: str) -> None` (line 1842) — renamed to `ensure_content_in_form`
- `_install_ajax_content_interceptor(sb, markdown_text: str) -> None` (line 1767) — renamed to `install_ajax_content_interceptor`

**Dependencies**: SeleniumBase (`sb` parameter), `dom_selectors`

### 5. `api_publisher.py` (~300 LOC)

**Responsibility**: Publishing posts via Tistory API (XHR) and React Redux state fallback.

**Functions**:
- `_publish_via_api(sb, blog_name, title, ...) -> str | None` (line 464) — renamed to `publish_via_api`
- `_call_tistory_post_api(sb, blog_name, ...) -> str | None` (line 500) — renamed to `call_tistory_post_api`
- `_try_publish_via_react_state(sb, blog_name, ...) -> str | None` (line 641) — renamed to `try_publish_via_react_state`

**Dependencies**: SeleniumBase, `json`, `re`, `time`, `form_filler` (for `safe_click`, `select_public_mode`, `select_category_in_layer`), `publish_verifier` (for `check_publish_layer_opened`, `click_publish_confirm_in_modal`), `src.domain.exceptions.DailyPublishLimitError`

**Note**: `_try_publish_via_react_state` has cross-module calls to `form_filler` and `publish_verifier` because the React fallback path requires UI interaction (selecting visibility, category, clicking confirm) after triggering the React publish action.

### 6. `publish_verifier.py` (~270 LOC)

**Responsibility**: Post-publication verification, URL extraction, visibility fixing.

**Functions**:
- `_verify_published_url(url: str, timeout: int = 10) -> int` (line 1574) — renamed to `verify_published_url`
- `_fix_post_visibility(sb, blog_name: str, published_url: str) -> bool` (line 1606) — renamed to `fix_post_visibility`
- `_extract_published_url(sb, blog_name: str) -> str | None` (line 1547) — renamed to `extract_published_url`
- `_extract_post_id(url: str) -> str | None` (line 1600) — renamed to `extract_post_id`
- `_check_publish_layer_opened(sb) -> str | None` (line 164) — renamed to `check_publish_layer_opened`
- `_click_publish_confirm_in_modal(sb, blog_name: str) -> str | None` (line 805) — renamed to `click_publish_confirm_in_modal`
- `_verify_faq_schema(url: str, timeout: int = 10) -> bool` (line 1812) — renamed to `verify_faq_schema`

**Dependencies**: SeleniumBase (some functions), `urllib.request` (HTTP verification), `re`, `form_filler` (for `safe_click` used by `click_publish_confirm_in_modal`)

### 7. `tistory_editor.py` (shrunk, ~290 LOC orchestrator)

**Responsibility**: Orchestration only. Coordinates the 6 modules to implement `publish_post()` and `update_post()`.

**Retained functions**:
- `publish_post(sb, post, blog_name, profile=None) -> PublishResult` — orchestrator
- `update_post(sb, post, blog_name, profile=None) -> PublishResult` — orchestrator
- `set_site_profile(profile)` — global profile setter (deprecated, kept for backward compat)
- `_get_profile(profile=None)` — profile resolution
- `_resolve_category_id(category_name, profile=None)` — category lookup

**New imports**: All 6 new modules via explicit imports.

**Deleted functions**:
- `_switch_to_markdown_mode()` (lines 889-995, 105 LOC) — deprecated, unused
- `_inject_markdown_content()` (lines 996-1135, 138 LOC) — deprecated, unused

## Naming Convention

Functions that move to their own module drop the leading underscore since they become the module's public API. Example: `_add_lazy_loading` in tistory_editor.py becomes `add_lazy_loading` in html_transformer.py. The orchestrator calls them as `html_transformer.add_lazy_loading(...)`.

## Import Pattern

The orchestrator (`tistory_editor.py`) imports submodules:

```python
from src.infrastructure.browser import markdown_converter
from src.infrastructure.browser import html_transformer
from src.infrastructure.browser import form_filler
from src.infrastructure.browser import content_injector
from src.infrastructure.browser import api_publisher
from src.infrastructure.browser import publish_verifier
```

Functions are called via module-qualified names for clarity:

```python
html = markdown_converter.convert_markdown_to_html(post.body_markdown)
html = html_transformer.add_lazy_loading(html)
content_injector.inject_html_content(sb, html)
```

## Affected Callers

### 1. `selenium_adapter.py` — No changes needed
```python
from src.infrastructure.browser.tistory_editor import publish_post, update_post  # unchanged
```

### 2. `cli.py` — No changes needed
```python
from src.infrastructure.browser.tistory_editor import set_site_profile  # retained in orchestrator
```

### 3. `adsense_pages.py` — Must update import
```python
# Before:
from src.infrastructure.browser.tistory_editor import _call_tistory_post_api
# After:
from src.infrastructure.browser.api_publisher import call_tistory_post_api
```

### 4. `tests/unit/infrastructure/test_markdown_to_html.py` — Must update imports
```python
# Before:
from src.infrastructure.browser.tistory_editor import (
    _add_lazy_loading, _add_nofollow_to_external_links,
    _extract_post_id, _style_mermaid_fallback,
    _verify_faq_schema, _verify_published_url,
    convert_markdown_to_html, validate_html,
)
# After:
from src.infrastructure.browser.markdown_converter import convert_markdown_to_html
from src.infrastructure.browser.html_transformer import (
    add_lazy_loading, add_nofollow_to_external_links, validate_html,
)
from src.infrastructure.browser.publish_verifier import (
    extract_post_id, verify_faq_schema, verify_published_url,
)
# Note: _style_mermaid_fallback stays internal to markdown_converter,
# test may need to import it as markdown_converter._style_mermaid_fallback
# or the test can be rewritten to test convert_markdown_to_html output.
```

## File Map

| File | Status | ~LOC |
|------|--------|------|
| `src/infrastructure/browser/markdown_converter.py` | Create | 120 |
| `src/infrastructure/browser/html_transformer.py` | Create | 100 |
| `src/infrastructure/browser/form_filler.py` | Create | 270 |
| `src/infrastructure/browser/content_injector.py` | Create | 215 |
| `src/infrastructure/browser/api_publisher.py` | Create | 300 |
| `src/infrastructure/browser/publish_verifier.py` | Create | 270 |
| `src/infrastructure/browser/tistory_editor.py` | Modify (shrink) | 290 |
| `src/infrastructure/browser/adsense_pages.py` | Modify (import fix) | — |
| `tests/unit/infrastructure/test_markdown_to_html.py` | Modify (import fix) | — |

## Verification

1. `make test-unit` — all existing tests pass (zero behavioral change)
2. `make lint` — 0 warnings
3. `make typecheck` — 0 errors
4. `make validate-ddd` — 0 violations (all modules stay in Infrastructure)
5. No new tests needed for this refactoring (pure structural, no logic changes)
