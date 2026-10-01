# 티스토리 목차 · 네이버 이웃 CTA · 미리보기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 티스토리 본문 변환을 함수 하나로 모으고, 목차를 다듬고, 글 끝에 네이버 이웃 추가 CTA를 붙이고, 통합 대시보드 티스토리 탭에서 최종 본문을 미리 본다.

**Architecture:** `tistory_editor`에 두 벌 복사된 변환 단계를 순수 함수 `render_tistory_html`(새 모듈 `tistory_render.py`)로 옮기고 발행·수정 발행·미리보기가 공유한다. CTA 주소는 `Config.naver_blog_url` → `SeleniumBrowserAdapter(cta_url)` → `publish_post/update_post(cta_url)`로 전달한다. 미리보기는 `create_app(preview_raw=True)`일 때 sandbox CSP를 건 독립 문서로 응답한다.

**Tech Stack:** Python 3.9 타깃, Python-Markdown(toc `slugify_unicode`), BeautifulSoup, Flask, pytest.

**Spec:** `docs/superpowers/specs/2026-10-01-tistory-toc-cta-preview-design.md`

## Global Constraints

- 모든 작업은 워크트리 `/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation/.claude/worktrees/naver-pipeline` 안에서만 한다. 운영 폴더(`/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation/` 바로 아래)는 읽기만 하고 절대 쓰지 않는다. `launchctl`·`~/Library/LaunchAgents`는 건드리지 않는다. 실제 발행·브라우저 실행 금지.
- `.env`는 내용을 출력하거나 보고에 옮기지 않는다(Task 4 Step 4에서 python-dotenv로 읽기만 허용).
- 새 의존성 추가 금지.
- 사용자에게 보이는 문구·로그·주석은 한국어. CTA 문구는 정확히: 안내 `IT·AI 실무 글을 네이버 블로그에도 올립니다. 이웃 추가하고 새 글 받아 보세요.` / 버튼 `네이버 블로그 이웃 추가`.
- CTA 링크: `https://blog.naver.com/<NAVER_BLOG_ID>`, `NAVER_BLOG_ID`가 `^[A-Za-z0-9_-]+$`일 때만. 아니면 CTA 없음. `target="_blank" rel="noopener"`.
- 미리보기 응답 CSP는 정확히: `sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`. 네이버 미리보기와 다른 모든 페이지의 CSP는 그대로.
- Task 1은 출력이 한 글자도 바뀌면 안 된다(골든 파일).
- 품질: `python -m pytest tests/unit -q` 전부 통과, `ruff check src/ tests/` 0건, `mypy src/ --ignore-missing-imports` 기준선 16건에서 늘지 않음.
- 커밋 형식 `refactor(infra): …`·`feat(infra): …`·`feat(web): …`, 본문 끝에 정확히 두 줄:
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01FqjKkJHg262ucm1vLLcPUi`

## 파일 구조

| 파일 | 역할 |
|------|------|
| `src/infrastructure/browser/tistory_render.py` (생성) | `render_tistory_html(post, blog_name, cta_url="")` |
| `src/infrastructure/browser/tistory_editor.py` (수정) | 두 경로가 `render_tistory_html` 사용, `cta_url` 인자 |
| `src/infrastructure/browser/markdown_converter.py` (수정) | 목차 제목 요소, `slugify_unicode` |
| `src/infrastructure/seo/inline_styler.py` (수정) | 목차 제목 스타일 대상 |
| `src/infrastructure/browser/html_transformer.py` (수정) | `append_naver_cta` |
| `src/infrastructure/config.py` (수정) | `naver_blog_url` 속성 |
| `src/infrastructure/browser/selenium_adapter.py` (수정) | `cta_url` 생성자 인자 전달 |
| `src/interface/cli.py`, `src/interface/web/platform.py` (수정) | 어댑터에 `cta_url=config.naver_blog_url` |
| `src/interface/web/app.py`, `templates/preview_raw.html`(생성), `__main__.py` (수정) | 티스토리 미리보기 |
| `tests/unit/infrastructure/test_tistory_render.py`, `tests/fixtures/tistory_render_golden.html` (생성) | 골든·CTA 테스트 |

---

### Task 1: 본문 변환을 `render_tistory_html` 하나로 (동작 불변)

**Files:**
- Create: `src/infrastructure/browser/tistory_render.py`
- Create: `tests/unit/infrastructure/test_tistory_render.py`, `tests/fixtures/tistory_render_golden.html`
- Modify: `src/infrastructure/browser/tistory_editor.py` (`publish_post`의 "MD→HTML 변환"부터 `apply_inline_styles`까지, `update_post`의 같은 구간)

**Interfaces:**
- Produces: `render_tistory_html(post: Post, blog_name: str, cta_url: str = "") -> str` — Task 1에서는 `cta_url`을 받기만 하고 쓰지 않는다(Task 3에서 사용). `publish_post/update_post(sb, post, blog_name, profile=None, cta_url="")`. 테스트 헬퍼 `sample_post()`·`GOLDEN`은 `tests/unit/infrastructure/test_tistory_render.py` 안에 둔다.

- [ ] **Step 1: 골든 파일 만들기 (코드 수정 전에)**

워크트리에서, 코드를 고치기 전에 아래 스크립트를 저장소 밖 임시 경로(예: `$(mktemp -d)/make_golden.py`, 커밋하지 않음)에 저장하고 워크트리를 현재 디렉터리로 해서 실행한다. 지금 `publish_post`의 변환 단계를 그대로 따라 한다.

```python
import sys
from pathlib import Path

sys.path.insert(0, ".")
from src.domain.entities.post import Post
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.browser import html_transformer, markdown_converter
from src.infrastructure.seo.html_optimizer import optimize_html
from src.infrastructure.seo.inline_styler import apply_inline_styles
from src.infrastructure.seo.internal_linker import inject_internal_links

BODY = (
    "## IaC란?\n\nIaC는 인프라를 코드로 관리합니다. Terraform을 많이 씁니다.\n\n"
    "![다이어그램](https://example.com/a.png)\n\n"
    "## 작동 원리\n\n### 선언형\n\n원하는 상태를 적습니다. "
    "[공식 문서](https://developer.hashicorp.com/terraform)\n\n"
    "```python\nprint('hi')\n```\n\n"
    "| 도구 | 방식 |\n|---|---|\n| Terraform | 선언형 |\n\n"
    "## FAQ\n\n**Q. 어렵나요?**\n\n아닙니다.\n"
)
post = Post(
    row_index=7, keyword="IaC란", status=PostStatus.PENDING,
    content=PostContent(
        title="IaC란? 개념 정리", body_markdown=BODY,
        meta_description="IaC 개념과 작동 원리를 정리했습니다.",
        faq_schema='[{"question": "어렵나요?", "answer": "아닙니다."}]',
        internal_link_keywords='["Terraform"]',
    ),
    quality_score=90,
)
post.internal_link_map = {"Terraform": "https://kimsanghyeon.tistory.com/100"}


class _LinkPost:
    def __init__(self, kw, url):
        self.keyword = kw
        self.published_url = url


content = post.content
html = markdown_converter.convert_markdown_to_html(content.body_markdown)
html = html_transformer.insert_summary_lead(html, content.meta_description)
html = html_transformer.add_lazy_loading(html)
html = html_transformer.add_nofollow_to_external_links(html, "kimsanghyeon")
links = [_LinkPost(k, u) for k, u in post.internal_link_map.items()]
html = inject_internal_links(html, content.internal_keyword_list(), links)
faq = content.faq_ld_json()
if faq:
    html = html_transformer.append_faq_schema(html, faq)
html = optimize_html(html)
html = apply_inline_styles(html)
Path("tests/fixtures").mkdir(parents=True, exist_ok=True)
Path("tests/fixtures/tistory_render_golden.html").write_text(html, encoding="utf-8")
print(len(html))
```

확인: 파일이 생기고, 안에 `toc-container`, `application/ld+json`, `kimsanghyeon.tistory.com/100`이 모두 들어 있다(`grep -c`). 하나라도 없으면 샘플이 그 단계를 타지 못한 것이니 BLOCKED로 보고한다.

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/unit/infrastructure/test_tistory_render.py`:

```python
"""티스토리 본문 변환 — 발행·수정 발행·미리보기가 같은 함수를 쓴다."""
from __future__ import annotations

from pathlib import Path

from src.domain.entities.post import Post
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.browser.tistory_render import render_tistory_html

GOLDEN = Path(__file__).resolve().parents[2] / "fixtures" / "tistory_render_golden.html"
BODY = (
    "## IaC란?\n\nIaC는 인프라를 코드로 관리합니다. Terraform을 많이 씁니다.\n\n"
    "![다이어그램](https://example.com/a.png)\n\n"
    "## 작동 원리\n\n### 선언형\n\n원하는 상태를 적습니다. "
    "[공식 문서](https://developer.hashicorp.com/terraform)\n\n"
    "```python\nprint('hi')\n```\n\n"
    "| 도구 | 방식 |\n|---|---|\n| Terraform | 선언형 |\n\n"
    "## FAQ\n\n**Q. 어렵나요?**\n\n아닙니다.\n"
)


def sample_post() -> Post:
    post = Post(
        row_index=7, keyword="IaC란", status=PostStatus.PENDING,
        content=PostContent(
            title="IaC란? 개념 정리", body_markdown=BODY,
            meta_description="IaC 개념과 작동 원리를 정리했습니다.",
            faq_schema='[{"question": "어렵나요?", "answer": "아닙니다."}]',
            internal_link_keywords='["Terraform"]',
        ),
        quality_score=90,
    )
    post.internal_link_map = {"Terraform": "https://kimsanghyeon.tistory.com/100"}
    return post


def test_변환_결과는_골든_파일과_같다():
    assert render_tistory_html(sample_post(), "kimsanghyeon") == GOLDEN.read_text(encoding="utf-8")


def test_내부_링크_매핑이_없으면_링크를_넣지_않는다():
    post = sample_post()
    post.internal_link_map = None
    assert "kimsanghyeon.tistory.com/100" not in render_tistory_html(post, "kimsanghyeon")
```

Run: `python -m pytest tests/unit/infrastructure/test_tistory_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.infrastructure.browser.tistory_render'`

- [ ] **Step 3: 구현**

`src/infrastructure/browser/tistory_render.py`:

```python
"""티스토리 본문 HTML 변환 — 발행·수정 발행·대시보드 미리보기가 같이 쓴다(브라우저 없음)."""
from __future__ import annotations

import logging

from src.domain.entities.post import Post
from src.infrastructure.browser import html_transformer, markdown_converter
from src.infrastructure.seo.html_optimizer import optimize_html
from src.infrastructure.seo.inline_styler import apply_inline_styles
from src.infrastructure.seo.internal_linker import inject_internal_links

logger = logging.getLogger(__name__)


class _LinkPost:
    def __init__(self, keyword: str, url: str):
        self.keyword = keyword
        self.published_url = url


def render_tistory_html(post: Post, blog_name: str, cta_url: str = "") -> str:
    """마크다운 본문 → 에디터에 넣을 최종 HTML. post.content가 있어야 한다."""
    content = post.content
    assert content is not None
    html_body = markdown_converter.convert_markdown_to_html(content.body_markdown or "")
    # 요약 문단: Tistory는 본문 첫 텍스트로 meta description을 자동 생성
    html_body = html_transformer.insert_summary_lead(html_body, content.meta_description)
    html_body = html_transformer.add_lazy_loading(html_body)
    html_body = html_transformer.add_nofollow_to_external_links(html_body, blog_name)

    if post.internal_link_map:
        link_posts = [_LinkPost(kw, url) for kw, url in post.internal_link_map.items()]
        keywords = content.internal_keyword_list()
        prev_len = len(html_body)
        html_body = inject_internal_links(html_body, keywords, link_posts)
        logger.info(
            f"내부 링크 삽입: keywords={len(keywords)}, "
            f"published={len(link_posts)}, body: {prev_len}→{len(html_body)}자"
        )

    if not html_transformer.validate_html(html_body):
        logger.warning("HTML 변환 검증 실패 — 그대로 진행")

    faq_ld_json = content.faq_ld_json()
    if faq_ld_json:
        html_body = html_transformer.append_faq_schema(html_body, faq_ld_json)

    # 반응형 + 성능 최적화 (img lazy/decoding, iframe lazy, preconnect)
    html_body = optimize_html(html_body)
    return apply_inline_styles(html_body)
```

`tistory_editor.py`:
- `publish_post` 시그니처를 `(sb, post: Post, blog_name: str, profile: SiteProfile | None = None, cta_url: str = "")`로, `update_post`도 같은 꼴로 바꾼다.
- `publish_post` 안의 `# --- MD→HTML 변환 ...` 줄부터 `html_body = apply_inline_styles(html_body)` 줄까지(내부 링크 블록·검증·FAQ 포함)를 `html_body = render_tistory_html(post, blog_name, cta_url)` 한 줄로 바꾼다.
- `update_post` 안의 `# MD→HTML 변환 (publish_post와 동일 파이프라인)` 줄부터 `html_body = apply_inline_styles(html_body)` 줄까지를 같은 한 줄로 바꾼다. (이전 `update_post`에는 `validate_html` 경고와 내부 링크 로그가 없었다 — 이제 생긴다. 로그뿐이라 출력 HTML은 같다.)
- 더 이상 안 쓰는 import(`markdown_converter`, `optimize_html`, `apply_inline_styles` 등)와 지역 변수(`body_markdown`이 안 쓰이게 되면)는 지운다. `html_transformer`는 `extract_first_image_url` 때문에 남는다. `ruff check --fix src/infrastructure/browser/tistory_editor.py`로 확인.
- import 추가: `from src.infrastructure.browser.tistory_render import render_tistory_html`

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/unit/infrastructure/test_tistory_render.py -v && python -m pytest tests/unit -q && ruff check src/ tests/`
Expected: 전부 PASS. `grep -n "convert_markdown_to_html\|apply_inline_styles" src/infrastructure/browser/tistory_editor.py` 결과 없음.

- [ ] **Step 5: 커밋**

```bash
git add src/infrastructure/browser/tistory_render.py src/infrastructure/browser/tistory_editor.py tests/unit/infrastructure/test_tistory_render.py tests/fixtures/tistory_render_golden.html
git commit -m "refactor(infra): 티스토리 본문 변환을 render_tistory_html 하나로"
```

---

### Task 2: 목차 제목을 제목 아닌 요소로, 한글 앵커

**Files:**
- Modify: `src/infrastructure/browser/markdown_converter.py` (toc 설정, `toc_block`)
- Modify: `src/infrastructure/seo/inline_styler.py` (`_style_toc`)
- Modify: `tests/unit/infrastructure/test_markdown_to_html.py` (149행 `"<h2>목차</h2>"` 기대값), `tests/unit/infrastructure/test_inline_styler.py`
- Modify: `tests/fixtures/tistory_render_golden.html` (재생성)

**Interfaces:**
- Consumes: Task 1의 `sample_post()`, `GOLDEN`, `render_tistory_html`.
- Produces: 목차 블록 `<div class="toc-container"><p class="toc-title"><strong>목차</strong></p>{toc}</div>`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/infrastructure/test_markdown_to_html.py`에서 `assert "<h2>목차</h2>" in html`을 다음으로 바꾼다:

```python
    assert '<p class="toc-title"><strong>목차</strong></p>' in html
    assert "<h2>목차</h2>" not in html
```

같은 파일 끝에 추가(`convert_markdown_to_html` import 이름은 파일 상단의 기존 import를 따른다):

```python
def test_한글_소제목은_읽히는_앵커가_되고_목차_링크와_맞는다():
    html = convert_markdown_to_html("## 작동 원리\n\n본문\n\n## 장점과 한계\n\n본문")
    assert 'id="작동-원리"' in html
    assert 'href="#작동-원리"' in html
    assert 'id="장점과-한계"' in html
```

`tests/unit/infrastructure/test_inline_styler.py` 끝에 추가(이 파일이 `apply_inline_styles`를 import하지 않으면 추가):

```python
def test_목차_제목_문단에_스타일이_붙는다():
    html = ('<div class="toc-container"><p class="toc-title"><strong>목차</strong></p>'
            '<div class="toc"><ul><li><a href="#a">A</a></li></ul></div></div>')
    out = apply_inline_styles(html)
    title = out[out.find('<p class="toc-title"'):out.find("<strong>목차")]
    assert "font-size:18px" in title
```

Run: `python -m pytest tests/unit/infrastructure/test_markdown_to_html.py tests/unit/infrastructure/test_inline_styler.py -v`
Expected: 바뀐/새 테스트 FAIL

- [ ] **Step 2: 구현**

`markdown_converter.py`:
- import 추가: `from markdown.extensions.toc import slugify_unicode`
- `"toc": {"permalink": False, "toc_depth": "2-3"},` →
  ```python
          # 한글 소제목도 읽히는 앵커(#작동-원리) — 기본 slugify는 한글을 지워 #_1이 된다
          "toc": {"permalink": False, "toc_depth": "2-3", "slugify": slugify_unicode},
  ```
- `toc_block = f'<div class="toc-container"><h2>목차</h2>{toc_html}</div>\n\n'` →
  ```python
          # 목차 제목은 소제목이 아니다 — h2로 두면 문서 개요에 '목차'가 섞인다
          toc_block = (
              f'<div class="toc-container"><p class="toc-title"><strong>목차</strong></p>'
              f"{toc_html}</div>\n\n"
          )
  ```

`inline_styler.py` `_style_toc`에서

```python
        h2 = toc.find("h2")
        if h2 and h2.get_text(strip=True) == "목차":
            _merge_style(h2, _TOC_HEADING_STYLE)
```
를
```python
        title = toc.find("p", class_="toc-title")
        if title is not None:
            _merge_style(title, _TOC_HEADING_STYLE)
```
로 바꾼다.

- [ ] **Step 3: 골든 파일 재생성과 차이 확인**

```bash
python -c "
import sys; sys.path.insert(0, 'tests/unit/infrastructure'); sys.path.insert(0, '.')
from test_tistory_render import sample_post, GOLDEN
from src.infrastructure.browser.tistory_render import render_tistory_html
GOLDEN.write_text(render_tistory_html(sample_post(), 'kimsanghyeon'), encoding='utf-8')"
git diff tests/fixtures/tistory_render_golden.html
```

바뀐 것이 목차 제목(`<h2 ...>목차</h2>` → `<p class="toc-title" ...><strong>목차</strong></p>`)과 앵커(`id`/`href`가 `iac란`, `작동-원리`, `선언형` 같은 한글 이름) 뿐인지 확인한다. 다른 변화가 있으면 BLOCKED로 보고한다.

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/unit -q && ruff check src/ tests/`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/infrastructure/browser/markdown_converter.py src/infrastructure/seo/inline_styler.py tests/unit/infrastructure/test_markdown_to_html.py tests/unit/infrastructure/test_inline_styler.py tests/fixtures/tistory_render_golden.html
git commit -m "feat(infra): 목차 제목을 소제목에서 빼고 한글 앵커 사용"
```

---

### Task 3: 글 끝 네이버 이웃 추가 CTA

**Files:**
- Modify: `src/infrastructure/browser/html_transformer.py` (`append_naver_cta`)
- Modify: `src/infrastructure/browser/tistory_render.py` (`cta_url` 사용)
- Modify: `src/infrastructure/config.py` (`naver_blog_url` 속성)
- Modify: `src/infrastructure/browser/selenium_adapter.py` (생성자 `cta_url`, `publish_post`/`update_post` 호출에 전달)
- Modify: `src/interface/cli.py` (모든 `SeleniumBrowserAdapter(...)`), `src/interface/web/platform.py` (`make_browser`의 `SeleniumBrowserAdapter(...)`)
- Test: `tests/unit/infrastructure/test_tistory_render.py`, `tests/unit/infrastructure/test_config_naver.py`

**Interfaces:**
- Consumes: `render_tistory_html(post, blog_name, cta_url="")`, `publish_post/update_post(..., cta_url="")`, `sample_post()`(Task 1).
- Produces: `append_naver_cta(html_text: str, url: str) -> str`, `Config.naver_blog_url -> str`(property), `SeleniumBrowserAdapter(..., cta_url: str = "")`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/infrastructure/test_tistory_render.py` 상단 import에 `from src.infrastructure.browser.html_transformer import append_naver_cta`를 더하고, 파일 끝에 추가:

```python
CTA_URL = "https://blog.naver.com/sangpedia"


def test_CTA_주소가_없으면_그대로():
    assert append_naver_cta("<p>본문</p>", "") == "<p>본문</p>"


def test_CTA_블록은_문구와_새_탭_링크를_가진다():
    html = append_naver_cta("<p>본문</p>", CTA_URL)
    assert html.startswith("<p>본문</p>")
    assert 'href="https://blog.naver.com/sangpedia"' in html
    assert 'target="_blank"' in html and 'rel="noopener"' in html
    assert "IT·AI 실무 글을 네이버 블로그에도 올립니다. 이웃 추가하고 새 글 받아 보세요." in html
    assert ">네이버 블로그 이웃 추가</a>" in html


def test_CTA_주소는_이스케이프한다():
    assert '"><script>' not in append_naver_cta("<p>x</p>", 'https://x/"><script>')


def test_렌더링하면_CTA가_맨_끝에_붙는다():
    html = render_tistory_html(sample_post(), "kimsanghyeon", CTA_URL)
    assert html.rstrip().endswith("</div>")
    assert html.rfind("네이버 블로그 이웃 추가") > html.rfind("application/ld+json")


def test_CTA가_없으면_골든_그대로():
    assert render_tistory_html(sample_post(), "kimsanghyeon", "") == GOLDEN.read_text(encoding="utf-8")
```

`tests/unit/infrastructure/test_config_naver.py` 끝에 추가:

```python
@pytest.mark.parametrize("blog_id, expected", [
    ("sangpedia", "https://blog.naver.com/sangpedia"),
    ("", ""),
    ("bad/../id", ""),
])
def test_네이버_블로그_주소(monkeypatch, blog_id, expected):
    monkeypatch.setenv("NAVER_BLOG_ID", blog_id)
    assert Config.from_env().naver_blog_url == expected
```

Run: `python -m pytest tests/unit/infrastructure/test_tistory_render.py tests/unit/infrastructure/test_config_naver.py -v`
Expected: 새 테스트 FAIL (`ImportError: cannot import name 'append_naver_cta'`, `AttributeError: ... naver_blog_url`)

- [ ] **Step 2: 구현**

`html_transformer.py` — import에 `from html import escape` 추가, 파일 끝에:

```python
_CTA_TEXT = "IT·AI 실무 글을 네이버 블로그에도 올립니다. 이웃 추가하고 새 글 받아 보세요."
_CTA_BOX_STYLE = (
    "margin:48px 0 8px;padding:20px 24px;border:1px solid #e9ecef;"
    "border-radius:8px;background:#f8f9fa;text-align:center"
)
_CTA_TEXT_STYLE = "margin:0 0 12px;font-size:16px;color:#1a1a2e"
_CTA_BUTTON_STYLE = (
    "display:inline-block;padding:10px 20px;border-radius:6px;background:#03c75a;"
    "color:#fff;font-weight:700;text-decoration:none"
)


def append_naver_cta(html_text: str, url: str) -> str:
    """글 맨 끝에 네이버 블로그 이웃 추가 블록. url이 비면 그대로(설정 없음)."""
    if not url:
        return html_text
    return (
        f'{html_text}\n<div class="naver-cta" style="{_CTA_BOX_STYLE}">'
        f'<p style="{_CTA_TEXT_STYLE}">{_CTA_TEXT}</p>'
        f'<a href="{escape(url)}" target="_blank" rel="noopener" style="{_CTA_BUTTON_STYLE}">'
        f"네이버 블로그 이웃 추가</a></div>"
    )
```

`tistory_render.py` 마지막 줄 `return apply_inline_styles(html_body)`를:

```python
    html_body = apply_inline_styles(html_body)
    # 스타일러 뒤에 붙인다 — CTA는 자체 인라인 스타일을 가지고, 스타일러가 바꾸지 않게
    return html_transformer.append_naver_cta(html_body, cta_url)
```

`config.py` — `import re`(없으면) 추가, `Config` 안에:

```python
    @property
    def naver_blog_url(self) -> str:
        """티스토리 글 끝 CTA 링크. 블로그 주소 형식이 아니면 빈 문자열(CTA 없음)."""
        blog_id = self.naver_blog_id.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", blog_id):
            return ""
        return f"https://blog.naver.com/{blog_id}"
```

`selenium_adapter.py`:
- `__init__` 마지막 키워드 인자로 `cta_url: str = ""` 추가, 본문에 `self._cta_url = cta_url  # 티스토리 글 끝 네이버 이웃 CTA 주소 — 비면 붙이지 않는다`.
- `publish_post(...)`·`update_post(...)` 호출 인자에 `cta_url=self._cta_url,` 추가.

`cli.py` — 모든 `SeleniumBrowserAdapter(` 호출(약 201·244·523·601·746행)의 `notifier=_build_notification(),` 다음 줄에 `cta_url=config.naver_blog_url,` 추가. 각 함수 범위의 Config 변수 이름을 확인해서 쓴다(`grep -n "def _\|config" src/interface/cli.py`).

`web/platform.py` `make_browser`의 `SeleniumBrowserAdapter(` 호출에 `cta_url=config.naver_blog_url,` 추가.

- [ ] **Step 3: 통과 확인**

Run: `python -m pytest tests/unit -q && ruff check src/ tests/ && mypy src/ --ignore-missing-imports 2>&1 | tail -1`
Expected: 전부 PASS, ruff 0, mypy 16 이하. `grep -c "cta_url=config.naver_blog_url" src/interface/cli.py`가 `grep -c "SeleniumBrowserAdapter(" src/interface/cli.py`와 같다.

- [ ] **Step 4: 커밋**

```bash
git add src/infrastructure/browser/html_transformer.py src/infrastructure/browser/tistory_render.py src/infrastructure/config.py src/infrastructure/browser/selenium_adapter.py src/interface/cli.py src/interface/web/platform.py tests/unit/infrastructure/test_tistory_render.py tests/unit/infrastructure/test_config_naver.py
git commit -m "feat(infra): 티스토리 글 끝에 네이버 블로그 이웃 추가 CTA"
```

---

### Task 4: 통합 대시보드 티스토리 탭 미리보기

**Files:**
- Modify: `src/interface/web/app.py` (`PREVIEW_CSP`, `create_app(preview_raw=...)`, `_register_check_routes`, `preview_post` 라우트, flask import에 `make_response`)
- Create: `src/interface/web/templates/preview_raw.html`
- Modify: `src/interface/web/__main__.py` (`_tistory_preview`, `_build_app`의 `preview=`, `preview_raw=`)
- Test: `tests/unit/interface/test_web_app.py`

**Interfaces:**
- Consumes: `render_tistory_html(post, blog_name, cta_url)`(Task 1·3), `Config.naver_blog_url`(Task 3), 기존 `create_app(..., preview=...)`.
- Produces: `create_app(..., preview_raw: bool = False)`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/interface/test_web_app.py`의 `Harness.__init__`에 `preview=None, preview_raw=False` 매개변수를 추가하고 `create_app(...)` 호출에 `preview=preview, preview_raw=preview_raw,`를 넘긴다. 파일 끝에 추가:

```python
class TestRawPreview:
    BODY = ('<div class="naver-cta" style="background:#f8f9fa">'
            '<a href="https://blog.naver.com/x">네이버 블로그 이웃 추가</a></div>')

    def test_티스토리_미리보기는_sandbox_CSP로_최종_HTML을_그대로(self):
        h = Harness(preview=lambda post: self.BODY, preview_raw=True)
        h.login()
        resp = h.client.get("/posts/2/preview")
        assert resp.status_code == 200
        csp = resp.headers["Content-Security-Policy"]
        assert csp.startswith("sandbox; default-src 'none'; style-src 'unsafe-inline'")
        html = resp.get_data(as_text=True)
        assert self.BODY in html
        assert 'href="/posts/2"' in html  # 상세로 돌아가는 링크

    def test_네이버_미리보기는_기존_CSP(self):
        h = Harness(preview=lambda post: "<p>본문</p>")
        h.login()
        resp = h.client.get("/posts/2/preview")
        assert "default-src 'self'" in resp.headers["Content-Security-Policy"]

    def test_다른_페이지는_기존_CSP(self):
        h = Harness(preview=lambda post: self.BODY, preview_raw=True)
        h.login()
        assert "default-src 'self'" in h.client.get("/").headers["Content-Security-Policy"]
```

Run: `python -m pytest tests/unit/interface/test_web_app.py::TestRawPreview -v`
Expected: FAIL — `create_app() got an unexpected keyword argument 'preview_raw'`

- [ ] **Step 2: 구현**

`app.py`:
- flask import 목록에 `make_response` 추가.
- `SECURITY_HEADERS` 정의 아래:

```python
# 티스토리 미리보기: 블로그에 들어갈 HTML을 인라인 스타일째 보여 준다. sandbox라 스크립트·쿠키·폼은 막힌다
PREVIEW_CSP = (
    "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
```

- `create_app` 키워드 인자에 `preview_raw: bool = False,`(`preview` 다음) 추가. `_register_check_routes(app, list_posts, job_runner, preview, clock)` 호출과 그 함수 정의에 `preview_raw` 인자를 추가해 넘긴다.
- `preview_post` 라우트에서 `return render_template("preview.html", ...)` 바로 앞에:

```python
        if preview_raw:
            # 본문은 markdown_converter가 bleach로 정리한 HTML — 그래도 sandbox로 격리
            response = make_response(
                render_template("preview_raw.html", post=post, body_html=preview(post)),
            )
            response.headers["Content-Security-Policy"] = PREVIEW_CSP
            return response
```

(`security_headers` after_request는 `setdefault`라 이 값을 덮지 않는다.)

`templates/preview_raw.html`:

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>미리보기 · {{ post.keyword }}</title>
  <style>
    body { margin: 0; background: #fff; color: #333; font: 16px/1.8 -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", sans-serif; }
    main { max-width: 760px; margin: 0 auto; padding: 16px; }
    .note { font-size: 13px; color: #86868b; }
    img { max-width: 100%; height: auto; }
  </style>
</head>
<body>
  <main>
    <p class="note"><a href="{{ url_for('post_detail', row_index=post.row_index) }}">← {{ post.row_index }}행 게시물</a> · 블로그에 올라갈 본문 그대로입니다. '관련 글'과 내부 링크는 발행할 때 붙습니다.</p>
    <h1>{{ post.title }}</h1>
    {{ body_html|safe }}
  </main>
</body>
</html>
```

`__main__.py`:
- import 추가: `from src.infrastructure.browser.tistory_render import render_tistory_html`
- `_generation_snapshot` 근처에 추가:

```python
def _tistory_preview(repo: GoogleSheetsPostRepository, config: Config, row_index: int) -> str:
    """티스토리 탭 미리보기 — 발행과 같은 변환으로 최종 HTML. 관련 글은 발행 때 붙는다."""
    post = next((p for p in repo.find_all() if p.row_index == row_index), None)
    if post is None or post.content is None or not post.content.body_markdown:
        return "<p>본문이 없습니다.</p>"
    return render_tistory_html(post, config.tistory_blog, config.naver_blog_url)
```

- `_build_app`의 `preview=(...)` 인자를 다음으로 바꾸고 바로 아래에 `preview_raw`를 추가:

```python
        preview=(
            (lambda post: build_preview_html(post.keyword, post.body_markdown))
            if profile.name == "naver"
            else (lambda post: _tistory_preview(repo, config, post.row_index))
        ),
        preview_raw=profile.name != "naver",
```

- [ ] **Step 3: 통과 확인**

Run: `python -m pytest tests/unit -q && ruff check src/ tests/ && mypy src/ --ignore-missing-imports 2>&1 | tail -1`
Expected: 전부 PASS, ruff 0, mypy 16 이하.

- [ ] **Step 4: 시트 실데이터로 미리보기 렌더 확인(읽기 전용, 발행 없음)**

워크트리에서 운영 `.env`·자격증명을 읽기만 해서 티스토리 시트의 발행완료 글 한 건을 렌더해 파일로 저장한다:

```bash
PROD="/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation"
OUT="$(mktemp -d)"
python - "$PROD" "$OUT" <<'EOF'
import os, sys
prod, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(os.path.join(prod, ".env"))
os.environ["GOOGLE_CREDS"] = os.path.join(prod, "credentials.json")
from src.infrastructure.config import Config
from src.infrastructure.persistence.google_sheets_repo import GoogleSheetsPostRepository
from src.interface.web.__main__ import _tistory_preview
cfg = Config.from_env()
repo = GoogleSheetsPostRepository(creds_path=cfg.google_creds, sheet_name=cfg.sheet_name)
row = next(p.row_index for p in repo.find_published(limit=5))
html = _tistory_preview(repo, cfg, row)
open(os.path.join(out, "preview.html"), "w", encoding="utf-8").write(html)
print(row, len(html), "toc-title" in html, "naver-cta" in html, cfg.naver_blog_url != "")
EOF
echo "$OUT/preview.html"
```

Expected: `<row> <길이> True True True`. (`.env` 값과 HTML 본문을 출력하거나 보고에 옮기지 않는다. 출력 파일 경로만 보고한다.)

- [ ] **Step 5: 커밋**

```bash
git add src/interface/web/app.py src/interface/web/templates/preview_raw.html src/interface/web/__main__.py tests/unit/interface/test_web_app.py
git commit -m "feat(web): 통합 대시보드 티스토리 탭에 최종 본문 미리보기"
```

---

### 반영 (컨트롤러, 사용자 확인 후)

1. `feat/naver-pipeline` → `master` fast-forward, 운영 폴더에서 단위 테스트
2. 대시보드 재시작 `launchctl kickstart -k gui/$(id -u)/com.blog-automation.dashboard-hub`(자동 권한 검사가 막으면 사용자가 `!`로)
3. 폰에서 티스토리 탭 → 글 상세 → 미리보기로 목차·CTA 확인
4. 다음 09:00 자동 발행 글에서 한글 앵커·CTA가 티스토리 에디터를 거쳐 남았는지 확인(지워지면 `slugify_unicode`만 되돌림)
