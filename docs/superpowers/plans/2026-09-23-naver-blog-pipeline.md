# 네이버 블로그 고품질 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버 전용 키워드로 n8n이 네이버용 글을 생성·검증해 `naver_calendar` 탭에 쌓고, 관리자 대시보드(`--platform naver`)에서 사람이 승인한 글만 네이버에 발행한다.

**Architecture:** Python 쪽은 기존 발행 흐름(`PublishSelectedPostUseCase`)을 그대로 쓰고, 저장소가 탭을 고를 수 있게 하고 대시보드가 플랫폼별로 저장소·브라우저·쿼터를 바꿔 조립한다. n8n 쪽은 네이버 워크플로우를 손으로 만들지 않고, `scripts/build_naver_workflow.py`가 티스토리 워크플로우(`workflow_complete.json`)를 복사해 네이버용 노드 코드(`n8n/code_nodes/naver/*.js`)와 프롬프트(`n8n/prompts/prompt_naver_*.md`)를 주입해 `n8n/workflow_naver.json`을 만든다.

**Tech Stack:** Python 3.9 타깃(3.11 실행), pytest, gspread, SeleniumBase, Flask / n8n 1.x Code 노드(JavaScript), Node.js 25 내장 테스트 러너(`node --test`)

**Spec:** `docs/superpowers/specs/2026-09-23-naver-blog-pipeline-design.md`

## Global Constraints

- 작업 디렉토리: `/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation` (모든 명령은 여기서 실행)
- Python 3.9 호환 문법. `X | None`은 파일 첫 줄에 `from __future__ import annotations`가 있을 때만
- ruff line length 100, 규칙 E/F/W/I/N/UP/B/A/SIM. 테스트 함수명 한글 허용
- DDD 계층: Domain은 stdlib만, Application은 Domain만, Infrastructure는 Application import 금지, Interface는 전부 가능
- 로그·사용자 메시지·주석은 한국어
- 기존 티스토리 동작을 바꾸지 않는다: `worksheet` 기본값은 첫 탭, `--platform` 기본값은 `tistory`, launchd 스케줄은 건드리지 않는다
- 네이버 탭 이름 기본값 `naver_calendar`, 네이버 일일 쿼터 1건, 네이버 워크플로우 스케줄 `0 2 * * *`
- 네이버 블로그 아이디는 `NAVER_BLOG_ID` (로그인 아이디가 아니라 블로그 주소, 운영값 `sangpedia`)
- `.env`는 Claude가 쓰지 않는다. `.env.example`만 수정한다
- 각 Task 끝의 커밋 메시지 끝에 다음 두 줄을 붙인다:
  ```
  Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01FqjKkJHg262ucm1vLLcPUi
  ```
- 새 파일을 처음 만들거나 고칠 때 GateGuard 훅이 한 번 거부하고 사실 제시를 요구한다. 거부되면 ① 이 파일을 부르는 곳 ② 영향받는 공개 API ③ 데이터 스키마 ④ 사용자 지시 원문("구현 계획 작성해"에 따른 계획 실행)을 적고 같은 호출을 재시도한다

## File Structure

| 파일 | 책임 | Task |
|------|------|------|
| `src/infrastructure/persistence/google_sheets_repo.py` (수정) | `worksheet` 인자로 탭 선택 | 1 |
| `src/infrastructure/config.py` (수정) | `naver_blog_id`, `naver_sheet_tab`, `validate_naver()` | 2 |
| `src/application/use_cases/publish_selected_post.py` (수정) | 로그인 실패 메시지에서 플랫폼 이름 제거 | 3 |
| `src/infrastructure/browser/naver/editor.py`, `adapter.py` (수정) | 발행 여부 불명 메시지, 실패 스크린샷 | 4 |
| `src/interface/web/app.py`, `templates/base.html` (수정) | 화면 상단 이름(`brand_label`) | 5 |
| `src/interface/web/platform.py` (신규) | 플랫폼별 탭·쿼터·이름·브라우저 조립 | 6 |
| `src/interface/web/__main__.py` (수정) | `--platform` 인자 | 6 |
| `n8n/prompts/prompt_naver_*.md` (신규 5개) | 네이버 공통 규칙, 유형 E/F/G, 검증 H | 7 |
| `n8n/code_nodes/naver/*.js` (신규 6개) + `tests/*.test.js` | 네이버 노드 로직(순수 함수 + n8n 연결부) | 8 |
| `scripts/build_naver_workflow.py` (신규), `n8n/workflow_naver.json` (생성물) | 워크플로우 생성·최신 여부 검사 | 9 |
| `Makefile`, `CLAUDE.md`, spec (수정) | `test-n8n` 타깃, 운영 문서 | 10 |

---

### Task 1: 시트 저장소가 탭을 고를 수 있게 한다

**Files:**
- Modify: `src/infrastructure/persistence/google_sheets_repo.py:56-60`
- Test: `tests/unit/infrastructure/test_sheets_repo_worksheet.py` (신규)

**Interfaces:**
- Produces: `GoogleSheetsPostRepository(creds_path: str, sheet_name: str, worksheet: str = "")` — `worksheet`가 빈 값이면 첫 탭(`sheet1`), 아니면 그 이름의 탭

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/infrastructure/test_sheets_repo_worksheet.py`:

```python
"""GoogleSheetsPostRepository 탭 선택 — 네이버 글은 같은 파일의 naver_calendar 탭에 둔다."""
from __future__ import annotations

import pytest

from src.infrastructure.persistence import google_sheets_repo as repo_mod
from src.infrastructure.persistence.google_sheets_repo import GoogleSheetsPostRepository


class _FakeSpreadsheet:
    sheet1 = "first-tab"

    def worksheet(self, title: str) -> str:
        return f"tab:{title}"


class _FakeClient:
    def open(self, name: str) -> _FakeSpreadsheet:
        return _FakeSpreadsheet()


@pytest.fixture(autouse=True)
def _no_google(monkeypatch):
    monkeypatch.setattr(
        repo_mod.GoogleCredentials, "from_service_account_file",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(repo_mod.gspread, "authorize", lambda *args, **kwargs: _FakeClient())


def test_worksheet_미지정이면_첫_탭():
    repo = GoogleSheetsPostRepository(creds_path="c.json", sheet_name="keyword_calendar_v2")
    assert repo._sheet == "first-tab"


def test_worksheet_지정하면_그_탭():
    repo = GoogleSheetsPostRepository(
        creds_path="c.json", sheet_name="keyword_calendar_v2", worksheet="naver_calendar",
    )
    assert repo._sheet == "tab:naver_calendar"
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/unit/infrastructure/test_sheets_repo_worksheet.py -v`
Expected: `test_worksheet_지정하면_그_탭` FAIL — `TypeError: __init__() got an unexpected keyword argument 'worksheet'`

- [ ] **Step 3: 구현**

`google_sheets_repo.py`의 `__init__`를 다음으로 바꾼다:

```python
    def __init__(self, creds_path: str, sheet_name: str, worksheet: str = ""):
        creds = GoogleCredentials.from_service_account_file(creds_path, scopes=SCOPES)
        client = gspread.authorize(creds, http_client=BackOffHTTPClient)
        spreadsheet = client.open(sheet_name)
        # 빈 값이면 첫 탭(티스토리). 네이버 글은 같은 파일의 naver_calendar 탭에 둔다.
        self._sheet = spreadsheet.worksheet(worksheet) if worksheet else spreadsheet.sheet1
        self._header_row = 1  # 1행은 헤더
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/unit/infrastructure/test_sheets_repo_worksheet.py tests/unit/infrastructure/test_sheet_datetime.py -v`
Expected: 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/infrastructure/persistence/google_sheets_repo.py tests/unit/infrastructure/test_sheets_repo_worksheet.py
git commit -m "feat(infra): 시트 저장소가 탭 이름으로 워크시트를 고를 수 있게 한다"
```

---

### Task 2: 네이버 설정값

**Files:**
- Modify: `src/infrastructure/config.py`
- Modify: `.env.example`
- Test: `tests/unit/infrastructure/test_config_naver.py` (신규)

**Interfaces:**
- Produces: `Config.naver_blog_id: str`(기본 `""`), `Config.naver_sheet_tab: str`(기본 `"naver_calendar"`), `Config.validate_naver() -> None` (누락 시 `OSError`)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/infrastructure/test_config_naver.py`:

```python
"""네이버 설정 — NAVER_BLOG_ID는 로그인 아이디가 아니라 블로그 주소다."""
from __future__ import annotations

import pytest

from src.infrastructure.config import Config


@pytest.fixture
def creds_file(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    path.write_text("{}")
    monkeypatch.setenv("GOOGLE_CREDS", str(path))
    return path


def test_기본값(monkeypatch):
    monkeypatch.delenv("NAVER_BLOG_ID", raising=False)
    monkeypatch.delenv("NAVER_SHEET_TAB", raising=False)
    config = Config.from_env()
    assert config.naver_blog_id == ""
    assert config.naver_sheet_tab == "naver_calendar"


def test_환경변수_반영(monkeypatch):
    monkeypatch.setenv("NAVER_BLOG_ID", "sangpedia")
    monkeypatch.setenv("NAVER_SHEET_TAB", "naver_test")
    config = Config.from_env()
    assert config.naver_blog_id == "sangpedia"
    assert config.naver_sheet_tab == "naver_test"


def test_validate_naver_통과(monkeypatch, creds_file):
    monkeypatch.setenv("NAVER_BLOG_ID", "sangpedia")
    Config.from_env().validate_naver()


def test_validate_naver_블로그_아이디_누락(monkeypatch, creds_file):
    monkeypatch.delenv("NAVER_BLOG_ID", raising=False)
    with pytest.raises(OSError, match="NAVER_BLOG_ID"):
        Config.from_env().validate_naver()


def test_validate_naver_자격증명_파일_없음(monkeypatch, tmp_path):
    monkeypatch.setenv("NAVER_BLOG_ID", "sangpedia")
    monkeypatch.setenv("GOOGLE_CREDS", str(tmp_path / "없음.json"))
    with pytest.raises(OSError, match="GOOGLE_CREDS"):
        Config.from_env().validate_naver()
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/unit/infrastructure/test_config_naver.py -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'naver_blog_id'`

- [ ] **Step 3: 구현**

`config.py`의 `Config` 필드 마지막(`site_profile_path: str` 아래)에 추가:

```python
    naver_blog_id: str = ""
    naver_sheet_tab: str = "naver_calendar"
```

`from_env()`의 `cls(...)` 인자 마지막(`site_profile_path=...` 아래)에 추가:

```python
            naver_blog_id=os.getenv("NAVER_BLOG_ID", ""),
            naver_sheet_tab=os.getenv("NAVER_SHEET_TAB", "naver_calendar"),
```

`validate_pages()` 아래에 메서드 추가:

```python
    def validate_naver(self) -> None:
        """네이버 대시보드 전용 검증. 카카오·티스토리 값은 필요 없다."""
        missing = []
        if not self.naver_blog_id:
            missing.append("NAVER_BLOG_ID (블로그 주소의 아이디, 로그인 아이디 아님)")
        if not os.path.exists(self.google_creds):
            missing.append(f"GOOGLE_CREDS (파일 없음: {self.google_creds})")
        if missing:
            raise OSError(f"네이버 필수 환경 변수 누락: {', '.join(missing)}")
```

`.env.example`의 `TISTORY_BLOG=your-blog` 줄 아래에 추가:

```
# 네이버 블로그 (대시보드 --platform naver). 로그인 아이디가 아니라 blog.naver.com/<여기> 값
NAVER_BLOG_ID=your-naver-blog
NAVER_SHEET_TAB=naver_calendar
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/unit/infrastructure/test_config_naver.py tests/unit/infrastructure/test_config_validate_pages.py -v`
Expected: 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/infrastructure/config.py .env.example tests/unit/infrastructure/test_config_naver.py
git commit -m "feat(infra): 네이버 블로그 아이디·탭 설정 추가"
```

---

### Task 3: 수동 발행의 로그인 실패 메시지에서 'Tistory'를 뺀다

네이버 대시보드도 같은 Use Case를 쓰므로 "Tistory 로그인 실패"는 틀린 안내가 된다.

**Files:**
- Modify: `src/application/use_cases/publish_selected_post.py:117`
- Test: `tests/unit/application/test_publish_selected_post.py:139-144`

**Interfaces:**
- Produces: 로그인 실패 시 `ManualPublishResult.message == "로그인 실패 — 발행대기 유지"`

- [ ] **Step 1: 테스트 수정 (실패하게)**

`test_publish_selected_post.py`의 로그인 실패 테스트(139행 근처, `MockBrowserAdapter(login_success=False)`를 쓰는 테스트)에서 `assert "로그인" in result.message` 줄 아래에 추가:

```python
        assert "Tistory" not in result.message  # 네이버 대시보드도 같은 메시지를 쓴다
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/unit/application/test_publish_selected_post.py -v -k 로그인`
Expected: FAIL — `assert 'Tistory' not in 'Tistory 로그인 실패 — 발행대기 유지'`
(테스트 이름에 '로그인'이 없으면 `-k login`으로 찾는다)

- [ ] **Step 3: 구현**

`publish_selected_post.py` 117행:

```python
                    post.row_index, "로그인 실패 — 발행대기 유지",
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/unit/application/test_publish_selected_post.py -v`
Expected: 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/application/use_cases/publish_selected_post.py tests/unit/application/test_publish_selected_post.py
git commit -m "refactor(app): 수동 발행 로그인 실패 메시지에서 플랫폼 이름 제거"
```

---

### Task 4: 네이버 어댑터 — 발행 여부 불명 표시와 실패 스크린샷

발행 확인을 누른 뒤 URL을 못 받으면 실제로는 발행됐을 수 있다. 재시도하면 중복 발행이 되므로 사유에 "발행 여부 수동 확인 필요"를 남긴다. 실패 원인 파악을 위해 스크린샷을 남긴다.

**Files:**
- Modify: `src/infrastructure/browser/naver/editor.py` (`_wait_published_url`)
- Modify: `src/infrastructure/browser/naver/adapter.py`
- Test: `tests/unit/infrastructure/test_naver_adapter.py`

**Interfaces:**
- Consumes: 기존 `editor.NaverEditorError`, `editor.publish(sb, tags) -> str`
- Produces: `editor.PUBLISH_UNCONFIRMED = "발행 여부 수동 확인 필요"`, `NaverBrowserAdapter(..., screenshot_dir: str = "logs/naver")`

- [ ] **Step 1: 실패하는 테스트 작성**

`test_naver_adapter.py` 맨 아래에 추가:

```python
class _FakeSb:
    def __init__(self):
        self.screenshots: list[str] = []

    def save_screenshot(self, path: str) -> None:
        self.screenshots.append(path)


def test_실패하면_스크린샷을_남긴다(calls, monkeypatch, tmp_path):
    def broken(sb, html, plain):
        raise editor.NaverEditorError("본문 붙여넣기가 반영되지 않음")

    monkeypatch.setattr(editor, "paste_body", broken)
    adapter = NaverBrowserAdapter("myblog", draft_only=False, screenshot_dir=str(tmp_path))
    fake = _FakeSb()
    adapter._sb = fake
    adapter.publish(_post())
    assert len(fake.screenshots) == 1
    assert fake.screenshots[0].startswith(str(tmp_path))
    assert "row2" in fake.screenshots[0]


def test_브라우저가_없어도_스크린샷_단계에서_죽지_않는다(calls, monkeypatch, tmp_path):
    def broken(sb, html, plain):
        raise editor.NaverEditorError("실패")

    monkeypatch.setattr(editor, "paste_body", broken)
    adapter = NaverBrowserAdapter("myblog", draft_only=False, screenshot_dir=str(tmp_path))
    assert not adapter.publish(_post()).success  # _sb None — 예외 없이 실패 결과


def test_발행_URL_미확인은_수동_확인_필요로_표시(calls, monkeypatch):
    def unconfirmed(sb, tags):
        raise editor.NaverEditorError(
            f"발행 후 글 URL을 확인하지 못함 — {editor.PUBLISH_UNCONFIRMED}"
        )

    monkeypatch.setattr(editor, "publish", unconfirmed)
    result = NaverBrowserAdapter("myblog", draft_only=False).publish(_post())
    assert not result.success
    assert editor.PUBLISH_UNCONFIRMED in result.error
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/unit/infrastructure/test_naver_adapter.py -v`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'screenshot_dir'`, `AttributeError: ... has no attribute 'PUBLISH_UNCONFIRMED'`

- [ ] **Step 3: 구현 — editor.py**

`EDITOR_TIMEOUT` 상수 근처에 추가:

```python
# 발행 확인을 누른 뒤 URL을 못 받으면 실제로는 발행됐을 수 있다 — 재시도하면 중복 발행
PUBLISH_UNCONFIRMED = "발행 여부 수동 확인 필요"
```

`_wait_published_url`의 마지막 `raise`를 바꾼다:

```python
    raise NaverEditorError(
        f"발행 후 글 URL을 확인하지 못함 — {PUBLISH_UNCONFIRMED} "
        f"(현재: {sb.get_current_url()})"
    )
```

- [ ] **Step 4: 구현 — adapter.py**

상단 import에 `from datetime import datetime`과 `from pathlib import Path`를 추가한다.

`__init__` 시그니처와 본문:

```python
    def __init__(self, blog_id: str, profile_dir: str = DEFAULT_PROFILE_DIR,
                 headless: bool = False, draft_only: bool = True,
                 min_delay: int = 300, max_delay: int = 900,
                 screenshot_dir: str = "logs/naver"):
        # headless 기본 False: 네이버는 헤드리스 탐지가 강하다(참고 저장소 공통 권고)
        self._blog_id = blog_id
        self._profile_dir = os.path.abspath(profile_dir)
        self._headless = headless
        self._draft_only = draft_only
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._screenshot_dir = Path(screenshot_dir)
        self._sb = None
        self._sb_context = None
```

`publish()`의 `except` 블록을 바꾼다:

```python
        except editor.NaverEditorError as e:
            logger.error(f"네이버 발행 실패 [{post.keyword}]: {e}")
            self._save_failure_screenshot(post)
            return PublishResult.fail(str(e))
```

`_pause()` 위에 메서드 추가:

```python
    def _save_failure_screenshot(self, post: Post) -> None:
        if self._sb is None:
            return
        try:
            self._screenshot_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = self._screenshot_dir / f"{stamp}_row{post.row_index}.png"
            self._sb.save_screenshot(str(path))
            logger.info(f"실패 스크린샷: {path}")
        except Exception as e:
            # 진단용이라 실패해도 발행 결과를 바꾸지 않는다
            logger.warning(f"실패 스크린샷 저장 못함: {e}")
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/unit/infrastructure/test_naver_adapter.py tests/unit/infrastructure/test_naver_content.py -v && ruff check src/infrastructure/browser/naver`
Expected: 모두 PASS, ruff 0건

- [ ] **Step 6: 커밋**

```bash
git add src/infrastructure/browser/naver/ tests/unit/infrastructure/test_naver_adapter.py
git commit -m "feat(infra): 네이버 발행 실패 스크린샷과 발행 여부 불명 표시"
```

---

### Task 5: 대시보드 상단 이름을 바꿀 수 있게 한다

두 대시보드가 똑같이 보이면 어느 블로그에 발행하는지 헷갈린다.

**Files:**
- Modify: `src/interface/web/app.py` (`create_app`)
- Modify: `src/interface/web/templates/base.html:8,13`
- Test: `tests/unit/interface/test_web_app.py`

**Interfaces:**
- Produces: `create_app(..., brand_label: str = "블로그 관리자")` — 모든 페이지 `<title>`과 상단 브랜드에 표시

- [ ] **Step 1: 실패하는 테스트 작성**

`test_web_app.py` 맨 아래에 추가:

```python
def test_brand_label이_화면에_표시된다():
    repo = InMemoryPostRepository([_post(2, "MCP란")])
    app = create_app(
        authenticator=AdminAuthenticator("admin", generate_password_hash(PASSWORD)),
        list_posts=ListPostsUseCase(repo),
        job_runner=PublishJobRunner(
            publish=lambda row: ManualPublishResult(ManualPublishOutcome.PUBLISHED, row, "ok"),
        ),
        secret_key="test-secret-key-0123456789",
        brand_label="네이버 블로그 관리자",
    )
    app.config["TESTING"] = True
    html = app.test_client().get("/login").get_data(as_text=True)
    assert "네이버 블로그 관리자" in html
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/unit/interface/test_web_app.py -v -k brand_label`
Expected: FAIL — `TypeError: create_app() got an unexpected keyword argument 'brand_label'`

- [ ] **Step 3: 구현**

`app.py`의 `create_app` 인자 목록 마지막(`allowed_hosts` 아래)에 추가:

```python
    brand_label: str = "블로그 관리자",
```

`app.jinja_env.globals["csrf_token"] = _csrf_token` 줄 아래에 추가:

```python
    app.jinja_env.globals["brand_label"] = brand_label
```

`templates/base.html` 8행과 13행:

```html
  <title>{% block title %}{{ brand_label }}{% endblock %}</title>
```

```html
    <a class="brand" href="{{ url_for('index') }}">{{ brand_label }}</a>
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/unit/interface -v`
Expected: 모두 PASS (기존 테스트는 기본값 "블로그 관리자"로 동작)

- [ ] **Step 5: 커밋**

```bash
git add src/interface/web/app.py src/interface/web/templates/base.html tests/unit/interface/test_web_app.py
git commit -m "feat(cli): 대시보드 상단 이름을 설정할 수 있게 한다"
```

---

### Task 6: 대시보드 `--platform naver`

**Files:**
- Create: `src/interface/web/platform.py`
- Modify: `src/interface/web/__main__.py`
- Test: `tests/unit/interface/test_web_platform.py` (신규)

**Interfaces:**
- Consumes: Task 1 `GoogleSheetsPostRepository(..., worksheet=)`, Task 2 `Config.naver_blog_id / naver_sheet_tab / validate_naver()`, Task 4 `NaverBrowserAdapter(..., screenshot_dir=)`, Task 5 `create_app(..., brand_label=)`
- Produces:
  - `PlatformProfile(name: str, label: str, worksheet: str, daily_limit: int)` (frozen dataclass)
  - `resolve_platform(name: str, config: Config) -> PlatformProfile` — 모르는 이름이면 `ValueError`
  - `make_browser(profile, config, project_root: Path, notifier, site_profile) -> BrowserPort`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/interface/test_web_platform.py`:

```python
"""대시보드 플랫폼 조립 — 네이버는 별도 탭·쿼터 1건·네이버 어댑터."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.services.quota_manager import DEFAULT_DAILY_LIMIT
from src.infrastructure.browser.naver.adapter import NaverBrowserAdapter
from src.infrastructure.browser.selenium_adapter import SeleniumBrowserAdapter
from src.infrastructure.config import Config
from src.interface.web.platform import make_browser, resolve_platform


@pytest.fixture
def config(monkeypatch) -> Config:
    monkeypatch.setenv("NAVER_BLOG_ID", "sangpedia")
    monkeypatch.setenv("NAVER_SHEET_TAB", "naver_calendar")
    monkeypatch.setenv("TISTORY_BLOG", "myblog")
    return Config.from_env()


def test_tistory는_기존과_같다(config):
    profile = resolve_platform("tistory", config)
    assert profile.worksheet == ""
    assert profile.daily_limit == DEFAULT_DAILY_LIMIT


def test_naver는_별도_탭과_쿼터_1건(config):
    profile = resolve_platform("naver", config)
    assert profile.worksheet == "naver_calendar"
    assert profile.daily_limit == 1
    assert "네이버" in profile.label


def test_모르는_플랫폼은_거부(config):
    with pytest.raises(ValueError, match="velog"):
        resolve_platform("velog", config)


def test_naver_브라우저는_공개_발행_네이버_어댑터(config, tmp_path):
    browser = make_browser(resolve_platform("naver", config), config, Path(tmp_path), None, None)
    assert isinstance(browser, NaverBrowserAdapter)
    assert browser._draft_only is False
    assert browser._blog_id == "sangpedia"
    assert browser._profile_dir == str(tmp_path / ".browser_data_naver")


def test_tistory_브라우저는_셀레니움_어댑터(config, tmp_path):
    browser = make_browser(resolve_platform("tistory", config), config, Path(tmp_path), None, None)
    assert isinstance(browser, SeleniumBrowserAdapter)
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/unit/interface/test_web_platform.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.interface.web.platform'`

- [ ] **Step 3: 구현 — platform.py**

`src/interface/web/platform.py`:

```python
"""대시보드 플랫폼별 조립 값 — 티스토리(기본)와 네이버.

네이버는 같은 스프레드시트의 별도 탭을 쓰고, 계정 제재 위험 때문에 하루 1건만 발행한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.notification_port import NotificationPort
from src.domain.services.quota_manager import DEFAULT_DAILY_LIMIT
from src.domain.value_objects.credentials import Credentials
from src.domain.value_objects.site_profile import SiteProfile
from src.infrastructure.browser.naver.adapter import DEFAULT_PROFILE_DIR, NaverBrowserAdapter
from src.infrastructure.browser.selenium_adapter import SeleniumBrowserAdapter
from src.infrastructure.config import Config

NAVER_DAILY_LIMIT = 1


@dataclass(frozen=True)
class PlatformProfile:
    name: str
    label: str
    worksheet: str
    daily_limit: int


def resolve_platform(name: str, config: Config) -> PlatformProfile:
    if name == "tistory":
        return PlatformProfile("tistory", "티스토리 블로그 관리자", "", DEFAULT_DAILY_LIMIT)
    if name == "naver":
        return PlatformProfile(
            "naver", "네이버 블로그 관리자", config.naver_sheet_tab, NAVER_DAILY_LIMIT,
        )
    raise ValueError(f"지원하지 않는 플랫폼: {name} (tistory 또는 naver)")


def make_browser(
    profile: PlatformProfile,
    config: Config,
    project_root: Path,
    notifier: NotificationPort | None,
    site_profile: SiteProfile | None,
) -> BrowserPort:
    """1건 수동 발행용 브라우저 — 다음 발행 대기 없음."""
    if profile.name == "naver":
        return NaverBrowserAdapter(
            config.naver_blog_id,
            profile_dir=str(project_root / DEFAULT_PROFILE_DIR),
            draft_only=False,  # 대시보드 발행 = 사람이 승인한 공개 발행
            min_delay=0,
            max_delay=0,
            screenshot_dir=str(project_root / "logs" / "naver"),
        )
    credentials = Credentials(
        kakao_id=config.kakao_id, kakao_pw=config.kakao_pw, tistory_blog=config.tistory_blog,
    )
    return SeleniumBrowserAdapter(
        credentials=credentials,
        headless=config.headless,
        min_delay=0,
        max_delay=0,
        user_data_dir=str(project_root / ".browser_data"),
        site_profile=site_profile,
        # 2FA가 뜨면 브라우저 앞에 사람이 없다 — 즉시 알려야 승인할 수 있다
        notifier=notifier,
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/unit/interface/test_web_platform.py -v`
Expected: 모두 PASS

- [ ] **Step 5: 구현 — `__main__.py` 조립 변경**

import 정리: `from src.domain.value_objects.credentials import Credentials`와 `from src.infrastructure.browser.selenium_adapter import SeleniumBrowserAdapter`를 지우고 다음을 추가한다.

```python
from src.interface.web.platform import PlatformProfile, make_browser, resolve_platform
```

`_build_publisher`를 다음으로 바꾼다:

```python
def _build_publisher(  # type: ignore[no-untyped-def]
    config: Config, repo: GoogleSheetsPostRepository, profile: PlatformProfile,
):
    # 티스토리 카테고리 해석용 프로필은 티스토리에서만 읽는다 (cli.py와 동일)
    site_profile = _load_site_profile(config) if profile.name == "tistory" else None

    def publish(row_index: int) -> ManualPublishResult:
        use_case = PublishSelectedPostUseCase(
            repo=repo,
            browser=make_browser(
                profile, config, PROJECT_ROOT, build_notification(), site_profile,
            ),
            enricher=InternalLinkEnricher(InternalLinkService()),
            quota=QuotaManager(daily_limit=profile.daily_limit),
            lock=DirectoryPipelineLock(LOCK_DIR),
        )
        logger.info(f"[{profile.name}] 수동 발행 시작: row={row_index}")
        result = use_case.execute(row_index)
        logger.info(
            f"[{profile.name}] 수동 발행 결과: row={row_index} "
            f"{result.outcome.value} — {result.message}"
        )
        return result

    return publish
```

`_serve()`를 다음으로 바꾼다:

```python
def _serve(platform: str) -> int:
    try:
        settings = DashboardSettings.from_env(os.environ)
    except SettingsError as e:
        print(f"대시보드 설정 오류: {e}", file=sys.stderr)
        return 2

    config = Config.from_env()
    profile = resolve_platform(platform, config)
    if profile.name == "naver":
        config.validate_naver()
    else:
        config.validate()
    repo = GoogleSheetsPostRepository(
        creds_path=config.google_creds, sheet_name=config.sheet_name,
        worksheet=profile.worksheet,
    )
    app = create_app(
        authenticator=AdminAuthenticator(settings.admin_user, settings.admin_password_hash),
        list_posts=ListPostsUseCase(repo),
        job_runner=PublishJobRunner(publish=_build_publisher(config, repo, profile)),
        secret_key=settings.secret_key,
        secure_cookies=settings.secure_cookies,
        allowed_hosts=settings.allowed_hosts,
        brand_label=profile.label,
    )
    logger.info(f"{profile.label} 시작: http://{settings.host}:{settings.port}")
    app.run(host=settings.host, port=settings.port, debug=False, threaded=True, use_reloader=False)
    return 0
```

`main()`의 argparse에 인자를 추가하고 `_serve` 호출을 바꾼다:

```python
    parser.add_argument(
        "--platform", default="tistory", choices=["tistory", "naver"],
        help="발행할 블로그 (기본 tistory). naver는 naver_calendar 탭·하루 1건",
    )
```

```python
    return _serve(args.platform)
```

모듈 docstring 사용법에 한 줄 추가:

```
    python -m src.interface.web --platform naver  # 네이버 대시보드 (naver_calendar 탭)
```

- [ ] **Step 6: 전체 확인**

Run: `python -m pytest tests/unit -q && ruff check src/ tests/ && mypy src/ --ignore-missing-imports 2>&1 | tail -1 && python -m src.interface.web --help`
Expected: 단위 테스트 전부 PASS, ruff 0건, mypy 오류 수가 작업 전(15건)보다 늘지 않음, `--help`에 `--platform {tistory,naver}` 표시

- [ ] **Step 7: 커밋**

```bash
git add src/interface/web/platform.py src/interface/web/__main__.py tests/unit/interface/test_web_platform.py
git commit -m "feat(cli): 관리자 대시보드에 --platform naver 추가"
```

---

### Task 7: 네이버 프롬프트 5종

프롬프트는 테스트 대상 코드가 아니라 문서다. Task 9 생성 스크립트가 이 파일들을 워크플로우에 넣고, 그 테스트가 주입 여부를 확인한다.

**Files:**
- Create: `n8n/prompts/prompt_naver_common.md`
- Create: `n8n/prompts/prompt_naver_e_howto.md`
- Create: `n8n/prompts/prompt_naver_f_compare.md`
- Create: `n8n/prompts/prompt_naver_g_explain.md`
- Create: `n8n/prompts/prompt_naver_h_verification.md`

**Interfaces:**
- Produces: 생성 프롬프트 = `common` + 빈 줄 + `e|f|g`. 출력 JSON 키: `title, meta_description, faq_schema, references, tags, internal_link_keywords, content` (기존 Parse JSON Response와 같음). 검증 출력 JSON 키: `is_accurate, is_logical, is_complete, is_useful, is_in_depth, no_fabricated_experience, natural_keyword_use, has_unique_info, mobile_readable, quality_score, reason`

- [ ] **Step 1: `prompt_naver_common.md` 작성**

````markdown
# 네이버 블로그 공통 작성 규칙

당신은 IT·AI 도구를 업무에 쓰는 직장인 독자를 위해 네이버 블로그 글을 쓰는 작가입니다.
독자는 개발자가 아닐 수 있습니다. 전문 용어는 처음 나올 때 한 줄로 풀어 씁니다.

## 문체
- 해요체로 씁니다("~해요", "~예요"). 반말, 과장된 감탄사, 이모지 남발은 쓰지 않습니다
- 한 문단은 2~3문장, 250자 이내로 씁니다. 모바일 화면에서 한 번에 읽히는 길이입니다
- 문장은 짧게, 한 문장에 정보 하나만 담습니다

## 경험을 지어내지 않습니다 (가장 중요)
- "직접 써보니", "제가 해보니", "저희 팀은" 같은 1인칭 경험을 쓰지 않습니다. 당신은 그 경험을 하지 않았습니다
- 대신 판단과 팁으로 씁니다: "이럴 때는 ~하는 편이 안전해요", "처음 쓰는 분들이 자주 놓치는 부분은 ~예요"
- 수치·가격·버전은 확인된 것만 쓰고, 바뀔 수 있는 값은 "작성 기준일 기준"이라고 밝힙니다

## 키워드
- 제목 앞부분에 키워드를 그대로 1회 넣습니다
- 본문에는 키워드를 자연스럽게 3~6회만 씁니다. 한 문단에 두 번 넣지 않습니다
- 키워드를 나열하거나 문장을 억지로 비트는 것은 네이버가 명시한 저품질 신호입니다

## 구성
- 본문은 마크다운이며 공백 포함 3,000자 이상입니다
- `##` 소제목을 3개 이상 둡니다. 소제목만 읽어도 글 흐름이 보이게 합니다
- 코드 블록은 쓰지 않는 것이 원칙이고, 꼭 필요하면 1개까지만 씁니다
- 외부 링크는 공식 문서(제품 공식 사이트·공식 도움말)만 3개 이하로 둡니다. 다른 블로그 링크는 넣지 않습니다
- 마지막 소제목은 `## 자주 묻는 질문`이고, 질문 3개를 `###`로 씁니다

## 상위 글보다 나은 글
- 사용자 메시지의 "네이버 검색 상위 글"을 읽고, 거기에 없는 정보를 1개 이상 반드시 넣습니다
  (예: 흔한 실수와 해결법, 상황별 선택 기준, 비용·제한 사항, 대안 비교)
- 상위 글의 문장을 베끼거나 순서만 바꿔 쓰지 않습니다

## 출력 형식
반드시 아래 JSON 하나만 출력합니다. JSON 밖에 다른 글을 쓰지 않습니다.

```json
{
  "title": "키워드로 시작하는 제목 (25~40자)",
  "meta_description": "검색 결과에 보일 요약 (80~120자)",
  "faq_schema": [
    {"question": "질문1", "answer": "답변1 (80자 이상)"},
    {"question": "질문2", "answer": "답변2 (80자 이상)"},
    {"question": "질문3", "answer": "답변3 (80자 이상)"}
  ],
  "references": ["공식 문서 URL"],
  "tags": ["태그 8~12개"],
  "internal_link_keywords": ["관련 키워드1", "관련 키워드2", "관련 키워드3"],
  "content": "마크다운 본문 전체"
}
```
````

- [ ] **Step 2: `prompt_naver_e_howto.md` 작성**

```markdown
# 유형 E: 활용법·따라하기

이 키워드는 "어떻게 하는지"를 찾는 검색입니다 (예: 노션 AI 사용법, ChatGPT로 엑셀 자동화).

## 본문 구조
1. 도입 (소제목 없이 2~3문단): 어떤 상황에서 이 방법이 필요한지, 이 글을 읽으면 무엇을 할 수 있는지
2. `## 시작하기 전에 확인할 것`: 필요한 계정·요금제·권한을 목록으로
3. `## 단계별로 따라하기`: `### 1단계 ...` 형식으로 4~7단계. 각 단계는 "무엇을 누르는지 → 무엇이 보이는지" 순서
4. `## 자주 막히는 부분`: 흔한 실수 2~3개와 해결법. 상위 글에 없는 정보는 주로 여기에 넣습니다
5. `## 정리`: 핵심 세 줄 요약
6. `## 자주 묻는 질문`
```

- [ ] **Step 3: `prompt_naver_f_compare.md` 작성**

```markdown
# 유형 F: 도구 비교·추천

이 키워드는 두 가지 이상을 비교하는 검색입니다 (예: Claude vs ChatGPT 업무용, 노션 AI 옵시디언 차이).

## 본문 구조
1. 도입: 한 줄 결론을 먼저 씁니다 ("문서 작업 위주면 A, 자동화 연동이 중요하면 B가 맞아요")
2. `## 한눈에 비교`: 마크다운 표. 비교 항목 6행 이상 (가격, 강점, 약점, 한국어 품질, 연동, 사용 제한)
3. `## 이런 분께는 A가 맞아요`, `## 이런 분께는 B가 맞아요`: 상황별 추천 이유 (A, B는 실제 이름으로)
4. `## 고를 때 놓치기 쉬운 점`: 요금제 제한, 데이터 정책 등 상위 글에 없는 판단 기준
5. `## 자주 묻는 질문`

- 한쪽을 일방적으로 깎아내리지 않습니다. 각자의 약점을 사실대로 씁니다
```

- [ ] **Step 4: `prompt_naver_g_explain.md` 작성**

```markdown
# 유형 G: 개념 쉽게 설명

이 키워드는 용어의 뜻을 찾는 검색입니다 (예: MCP란, RAG 쉽게).

## 본문 구조
1. 도입: 일상 비유 하나로 시작합니다 ("RAG는 오픈북 시험과 비슷해요")
2. `## ○○란 무엇인가요` (○○는 실제 용어): 한 문장 정의 → 풀어 쓴 설명
3. `## 어떻게 작동하나요`: 3~5단계 흐름. 필요하면 목록으로
4. `## 실무에서는 이렇게 쓰여요`: 직장인이 체감할 사례 2~3개
5. `## 흔한 오해`: 헷갈리는 개념과의 차이. 사용자 메시지에 "내부 용어 정의"가 있으면 그 정의와 혼동 포인트를 반드시 반영합니다
6. `## 자주 묻는 질문`
```

- [ ] **Step 5: `prompt_naver_h_verification.md` 작성**

```markdown
# 네이버 블로그 글 품질 검증

당신은 네이버 블로그 글의 품질을 검증합니다. 아래 기준으로 평가하고 JSON 하나만 출력합니다.

## 평가 항목
- is_accurate: 사실 오류가 없는가 (버전, 가격, 기능 설명)
- is_logical: 흐름이 자연스럽고 소제목과 내용이 맞는가
- is_complete: 검색한 사람이 궁금해할 내용을 빠짐없이 다뤘는가
- is_useful: 읽고 나서 바로 써먹을 수 있는가
- is_in_depth: 뻔한 설명을 넘어 판단 기준과 주의점이 있는가
- no_fabricated_experience: "직접 써보니", "제가 해보니" 같은 지어낸 1인칭 경험이 없으면 true
- natural_keyword_use: 키워드가 억지로 반복되거나 문장이 어색하게 비틀리지 않았으면 true
- has_unique_info: 함께 준 "네이버 검색 상위 글"에 없는 정보가 1개 이상 있으면 true
- mobile_readable: 문단이 짧고(2~3문장) 소제목·목록으로 훑어보기 쉬우면 true

## 점수
quality_score는 0~100이며 70점 이상이면 발행 가능한 수준입니다.
평가 항목 중 하나라도 false면 quality_score는 69점 이하로 줍니다.

## 출력 형식
JSON 외 텍스트를 쓰지 않습니다. reason은 한국어 100자 이내입니다.

{"is_accurate": true, "is_logical": true, "is_complete": true, "is_useful": true, "is_in_depth": true, "no_fabricated_experience": true, "natural_keyword_use": true, "has_unique_info": true, "mobile_readable": true, "quality_score": 85, "reason": "사유"}
```

- [ ] **Step 6: 커밋**

```bash
git add n8n/prompts/prompt_naver_*.md
git commit -m "feat(n8n): 네이버 전용 생성·검증 프롬프트 추가"
```

---

### Task 8: 네이버 n8n 노드 코드 (순수 함수 + 연결부) 와 node 테스트

각 파일은 앞부분에 순수 함수를, 끝에 n8n 연결부를 둔다. `typeof $input === 'undefined'`(node 테스트 환경)이면 함수만 내보내고 끝낸다. n8n Code 노드와 Node의 CommonJS 모두 최상위 `return`을 허용한다.

**Files:**
- Create: `n8n/code_nodes/naver/parse_naver_search.js`
- Create: `n8n/code_nodes/naver/route_prompt_naver.js`
- Create: `n8n/code_nodes/naver/validate_structure_naver.js`
- Create: `n8n/code_nodes/naver/build_verify_request_naver.js`
- Create: `n8n/code_nodes/naver/parse_verification_naver.js`
- Create: `n8n/code_nodes/naver/check_duplicate_naver.js`
- Test: `n8n/code_nodes/naver/tests/naver_nodes.test.js`

**Interfaces:**
- Consumes (n8n 노드 이름, Task 9가 유지함): `Sheets Read (Status=대기)`, `Sheets Read (Published Keywords)`, `Sheets Read (Naver Published)`, `Sheets Read (Brain Terms)`, `Parse SERP Data`, `Route Prompt (A/B/C)`, `Validate Structure`
- Produces (다음 노드가 읽는 필드):
  - Parse SERP Data → `serp_text, top_posts[{title, description, link, postdate}], naver_result_total, search_ok, serp_urls: [], official_urls: []` + 시트 행 필드
  - Route Prompt (A/B/C) → `keyword, category, row_index, prompt_type('E'|'F'|'G'), system_prompt, user_message`
  - Validate Structure → 입력 + `structure_validation{passed, issues[], stats}`
  - Build Verify Request → 입력 + `system_prompt, user_message, _llm_purpose: 'verification'`
  - Parse Verification Result → 입력 + `verification{passed, quality_score, reason, llm_reason, 9개 항목 boolean}`
  - Check Duplicate → 입력 + `duplicate_check{is_duplicate, duplicate_of, max_overlap, threshold}`
- 주입 표식: `route_prompt_naver.js`의 `/*INJECT:PROMPTS*/ ... /*END:PROMPTS*/`, `build_verify_request_naver.js`의 `/*INJECT:VERIFY_PROMPT*/ ... /*END:VERIFY_PROMPT*/` (Task 9가 교체)

- [ ] **Step 1: 실패하는 node 테스트 작성**

`n8n/code_nodes/naver/tests/naver_nodes.test.js`:

```javascript
// 네이버 n8n 노드의 순수 함수 테스트 — 실행: node --test "n8n/code_nodes/naver/tests/*.test.js"
const test = require('node:test');
const assert = require('node:assert/strict');

const search = require('../parse_naver_search.js');
const route = require('../route_prompt_naver.js');
const structure = require('../validate_structure_naver.js');
const verifyReq = require('../build_verify_request_naver.js');
const verdict = require('../parse_verification_naver.js');
const dup = require('../check_duplicate_naver.js');

test('검색 결과: 태그·엔티티를 벗기고 상위 5개만', () => {
  const items = Array.from({ length: 7 }, (_, i) => ({
    title: `<b>MCP</b>란 ${i}`, description: '뜻&amp;예시', link: `https://blog.naver.com/a/${i}`, postdate: '20260901',
  }));
  const r = search.summarizeNaverBlogResults({ total: 120, items });
  assert.equal(r.topPosts.length, 5);
  assert.equal(r.topPosts[0].title, 'MCP란 0');
  assert.equal(r.topPosts[0].description, '뜻&예시');
  assert.equal(r.total, 120);
  assert.match(r.serpText, /^1\. MCP란 0/);
});

test('검색 결과: 비어 있으면 빈 목록', () => {
  const r = search.summarizeNaverBlogResults({ total: 0, items: [] });
  assert.equal(r.topPosts.length, 0);
  assert.equal(r.serpText, '');
});

test('프롬프트 유형: 비교 키워드는 F', () => {
  assert.equal(route.choosePromptType('Claude vs ChatGPT 업무용', '', false), 'F');
  assert.equal(route.choosePromptType('노션 AI 옵시디언 차이', '', false), 'F');
});

test('프롬프트 유형: 개념 키워드와 볼트 용어 정확 일치는 G', () => {
  assert.equal(route.choosePromptType('MCP란', '', false), 'G');
  assert.equal(route.choosePromptType('RAG 쉽게', '', false), 'G');
  assert.equal(route.choosePromptType('하네스', '', true), 'G');
});

test('프롬프트 유형: 나머지는 E', () => {
  assert.equal(route.choosePromptType('노션 AI 사용법', '', false), 'E');
});

test('볼트 용어: 부분 일치는 정확 일치가 아니다', () => {
  const rows = [{ 용어: 'AI', 별칭: '인공지능' }, { 용어: '하네스', 별칭: 'harness' }];
  assert.equal(route.isExactBrainTerm('노션 AI 사용법', rows), false);
  assert.equal(route.isExactBrainTerm('Harness', rows), true);
});

test('사용자 메시지에 상위 글과 용어 정의가 들어간다', () => {
  const msg = route.buildUserMessage({
    keyword: 'MCP란', yearMonth: '2026년 9월',
    topPosts: [{ title: 'MCP 총정리', description: '설명' }],
    brainCards: [{ 용어: 'MCP', 한줄정의: '모델 컨텍스트 프로토콜', 혼동포인트: 'MCP ≠ API' }],
  });
  assert.match(msg, /키워드: MCP란/);
  assert.match(msg, /1\. MCP 총정리/);
  assert.match(msg, /모델 컨텍스트 프로토콜/);
});

function goodContent(keyword) {
  const para = `${keyword}는 업무에 도움이 돼요. 짧은 문단으로 씁니다.`;
  const sections = ['시작하기 전에', '단계별로 따라하기', '자주 묻는 질문']
    .map((h) => `## ${h}\n\n${'가나다라마바사 아자차카타파하. '.repeat(8)}\n\n${'설명 문장입니다. '.repeat(10)}`);
  // 문단 하나가 300자를 넘지 않게 짧은 문단 20개로 채운다 (총 3,600자 안팎)
  const filler = Array.from({ length: 20 }, () => '본문 채우기 문장이에요. '.repeat(10)).join('\n\n');
  return [para, ...sections, `${keyword} 정리예요.`, filler].join('\n\n');
}

test('구조 검사: 좋은 글은 통과', () => {
  const r = structure.validateNaverStructure({
    title: '노션 AI 사용법 총정리', content: goodContent('노션 AI 사용법'), keyword: '노션 AI 사용법',
    tags: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'],
  });
  assert.deepEqual(r.issues, []);
  assert.equal(r.passed, true);
});

test('구조 검사: 키워드 반복 과다·외부 링크 과다·긴 문단·태그 부족을 잡는다', () => {
  const kw = '노션 AI 사용법';
  const content = goodContent(kw)
    + `\n\n${`${kw} `.repeat(7)}`
    + '\n\n[1](https://a.com) [2](https://b.com) [3](https://c.com) [4](https://d.com)'
    + `\n\n${'긴 문단입니다. '.repeat(60)}`;
  const r = structure.validateNaverStructure({ title: `${kw} 정리`, content, keyword: kw, tags: ['a'] });
  const joined = r.issues.join(' | ');
  assert.equal(r.passed, false);
  assert.match(joined, /키워드 반복 과다/);
  assert.match(joined, /외부 링크 과다/);
  assert.match(joined, /긴 문단/);
  assert.match(joined, /태그 수/);
});

test('구조 검사: 제목에 키워드가 없으면 실패', () => {
  assert.equal(structure.titleHasKeyword('업무 자동화 가이드', '노션 AI 사용법'), false);
  assert.equal(structure.titleHasKeyword('노션AI 사용법 정리', '노션 AI 사용법'), true);
});

test('검증 요청 메시지에 상위 글과 본문이 들어간다', () => {
  const msg = verifyReq.buildVerifyMessage({
    keyword: 'MCP란', title: 'MCP란 무엇인가요', content: '본문',
    topPosts: [{ title: '상위글', description: '요약' }],
  });
  assert.match(msg, /상위글 — 요약/);
  assert.match(msg, /제목: MCP란 무엇인가요/);
});

const ALL_TRUE = {
  is_accurate: true, is_logical: true, is_complete: true, is_useful: true, is_in_depth: true,
  no_fabricated_experience: true, natural_keyword_use: true, has_unique_info: true,
  mobile_readable: true, quality_score: 85, reason: '좋음',
};

test('판정: 모두 통과', () => {
  const v = verdict.judgeNaver(ALL_TRUE, { structurePassed: true, structureIssues: [], searchOk: true });
  assert.equal(v.passed, true);
  assert.equal(v.quality_score, 85);
});

test('판정: 경험 날조는 점수와 무관하게 실패', () => {
  const v = verdict.judgeNaver({ ...ALL_TRUE, no_fabricated_experience: false },
    { structurePassed: true, structureIssues: [], searchOk: true });
  assert.equal(v.passed, false);
  assert.match(v.reason, /no_fabricated_experience/);
});

test('판정: 네이버 항목 누락은 실패로 본다', () => {
  const { has_unique_info, ...missing } = ALL_TRUE;
  const v = verdict.judgeNaver(missing, { structurePassed: true, structureIssues: [], searchOk: true });
  assert.equal(v.passed, false);
});

test('판정: 구조 검사 실패와 검색 0건이 사유에 남는다', () => {
  const v = verdict.judgeNaver(ALL_TRUE, {
    structurePassed: false, structureIssues: ['소제목(H2) 부족'], searchOk: false,
  });
  assert.equal(v.passed, false);
  assert.match(v.reason, /네이버 검색 결과 0건/);
  assert.match(v.reason, /소제목\(H2\) 부족/);
});

test('LLM JSON 파싱: 앞뒤 텍스트와 후행 쉼표를 견딘다', () => {
  const r = verdict.parseLlmJson('결과:\n{"quality_score": 80, "reason": "ok",}\n끝');
  assert.equal(r.quality_score, 80);
});

test('중복 검사: 두 탭 키워드와 비교한다', () => {
  const existing = ['노션 AI 사용법', 'MCP란'];
  assert.equal(dup.findDuplicate('노션 AI 사용법 정리', existing).is_duplicate, true);
  assert.equal(dup.findDuplicate('MCP란', existing).is_duplicate, true);
  assert.equal(dup.findDuplicate('RAG 쉽게', existing).is_duplicate, false);
});
```

- [ ] **Step 2: 실패 확인**

Run: `node --test "n8n/code_nodes/naver/tests/*.test.js"`
Expected: FAIL — `Cannot find module '../parse_naver_search.js'`

- [ ] **Step 3: `parse_naver_search.js` 작성**

```javascript
/**
 * Parse SERP Data (네이버판) — 네이버 블로그 검색 결과를 프롬프트용으로 정리
 * Mode: runOnceForEachItem
 * 입력: Naver Blog Search 노드 응답 (openapi.naver.com/v1/search/blog.json)
 * 출력: 시트 행 + serp_text, top_posts, search_ok
 * 노드 이름은 'Parse SERP Data' 그대로 둔다 — URL Validation이 이 이름으로 serp_urls를 읽는다.
 */

const TOP_LIMIT = 5;

function stripTags(value) {
  return String(value || '')
    .replace(/<[^>]+>/g, '')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .trim();
}

function summarizeNaverBlogResults(response, limit = TOP_LIMIT) {
  const items = response && Array.isArray(response.items) ? response.items : [];
  const topPosts = items.slice(0, limit).map((it) => ({
    title: stripTags(it.title),
    description: stripTags(it.description),
    link: it.link || '',
    postdate: it.postdate || '',
  }));
  const serpText = topPosts
    .map((p, i) => `${i + 1}. ${p.title}\n   ${p.description}`)
    .join('\n');
  return { topPosts, serpText, total: Number((response && response.total) || 0) };
}

if (typeof $input === 'undefined') {
  module.exports = { stripTags, summarizeNaverBlogResults };
  return;
}

const summary = summarizeNaverBlogResults($input.item.json);
const sheetData = $('Sheets Read (Status=대기)').item.json;

return {
  json: {
    ...sheetData,
    serp_text: summary.serpText || '(네이버 검색 결과 없음)',
    top_posts: summary.topPosts,
    naver_result_total: summary.total,
    search_ok: summary.topPosts.length > 0,
    serp_urls: [],      // 경쟁 블로그 글은 인용하지 않는다
    official_urls: [],  // Fetch Official Docs는 건너뛴다
  },
};
```

- [ ] **Step 4: `route_prompt_naver.js` 작성**

```javascript
/**
 * Route Prompt (네이버판) — 키워드 유형별 네이버 프롬프트 선택 + 사용자 메시지 조립
 * Mode: runOnceForEachItem
 * 노드 이름은 'Route Prompt (A/B/C)' 그대로 둔다 — Parse JSON Response·Sheets Update가 참조한다.
 * PROMPTS는 scripts/build_naver_workflow.py가 n8n/prompts/prompt_naver_*.md로 채운다.
 */

const PROMPTS = /*INJECT:PROMPTS*/ { E: 'PROMPT_E', F: 'PROMPT_F', G: 'PROMPT_G' } /*END:PROMPTS*/;

const JSON_SAFETY_NOTE = `

## 중요: JSON 형식 규칙
- 반드시 유효한 JSON을 출력하세요.
- content 필드의 줄바꿈은 반드시 \\n으로 이스케이프하세요.
- 문자열 내 큰따옴표는 반드시 \\"으로 이스케이프하세요.
- 문자열 내 백슬래시는 반드시 \\\\로 이스케이프하세요.
`;

function termNames(row) {
  return [row['용어'], ...String(row['별칭'] || '').split(',')]
    .map((s) => String(s || '').trim().toLowerCase())
    .filter((s) => s.length > 1);
}

function matchBrainTerms(keyword, rows, limit = 3) {
  const kw = String(keyword || '').toLowerCase();
  return (rows || [])
    .filter((r) => termNames(r).some((n) => kw.includes(n) || n.includes(kw)))
    .slice(0, limit);
}

// 부분 일치로 유형을 정하면 'AI' 같은 짧은 용어가 대부분의 키워드를 G로 끌고 간다
function isExactBrainTerm(keyword, rows) {
  const kw = String(keyword || '').trim().toLowerCase();
  return (rows || []).some((r) => termNames(r).includes(kw));
}

function choosePromptType(keyword, category, exactBrainTerm) {
  const kw = String(keyword || '').toLowerCase();
  if (/vs|비교|차이/.test(kw) || String(category || '').includes('비교')) return 'F';
  if (exactBrainTerm || /(란|이란|뜻|개념|쉽게)(\s|$)/.test(kw)) return 'G';
  return 'E';
}

function formatTopPosts(topPosts) {
  if (!topPosts || topPosts.length === 0) return '(네이버 검색 결과 없음)';
  return topPosts.map((p, i) => `${i + 1}. ${p.title}\n   ${p.description}`).join('\n');
}

function buildUserMessage({ keyword, yearMonth, topPosts, brainCards }) {
  const brainSection = brainCards && brainCards.length
    ? '\n\n## 내부 용어 정의 (이 정의를 우선 적용하고, 혼동 포인트를 본문에서 짚을 것)\n'
      + brainCards.map((r) => `### ${r['용어']}\n- 정의: ${r['한줄정의']}\n- 혼동 포인트: ${r['혼동포인트'] || '-'}`).join('\n\n')
    : '';
  return `키워드: ${keyword}\n작성 기준일: ${yearMonth}${brainSection}`
    + `\n\n## 네이버 검색 상위 글 (이 글들에 없는 정보를 1개 이상 넣을 것, 문장 베끼기 금지)\n`
    + formatTopPosts(topPosts);
}

if (typeof $input === 'undefined') {
  module.exports = { PROMPTS, matchBrainTerms, isExactBrainTerm, choosePromptType, buildUserMessage };
  return;
}

const input = $input.item.json;
const keyword = input['키워드'] || '';
const brainRows = $('Sheets Read (Brain Terms)').all().map((i) => i.json);
const promptType = choosePromptType(keyword, input['콘텐츠유형'], isExactBrainTerm(keyword, brainRows));
const today = new Date();

return {
  json: {
    keyword,
    category: input['콘텐츠유형'] || '',
    row_index: input['__row_index'] || input['row_number'] || 0,
    prompt_type: promptType,
    system_prompt: PROMPTS[promptType] + JSON_SAFETY_NOTE,
    user_message: buildUserMessage({
      keyword,
      yearMonth: `${today.getFullYear()}년 ${today.getMonth() + 1}월`,
      topPosts: input.top_posts || [],
      brainCards: matchBrainTerms(keyword, brainRows),
    }),
  },
};
```

- [ ] **Step 5: `validate_structure_naver.js` 작성**

````javascript
/**
 * Validate Structure (네이버판) — 네이버 규칙을 코드로 검사
 * Mode: runOnceForEachItem
 * 입력: Parse JSON Response 출력 (title, content, tags)
 * 출력: 입력 + structure_validation { passed, issues, stats }
 * 여기서 실패하면 Parse Verification Result가 LLM 점수와 무관하게 검수필요로 보낸다.
 */

const LIMITS = {
  minLength: 3000,
  minH2: 3,
  minKeywordCount: 1,
  maxKeywordCount: 6,
  maxExternalLinks: 3,
  maxParagraphChars: 300,
  maxCodeBlocks: 1,
  minTags: 5,
  maxTags: 15,
};

// 제목·표·목록·인용·코드는 문단 길이 검사에서 뺀다
const NON_PARAGRAPH = /^(#|\||-|\*|>|```|\d+\.\s)/;

function countOccurrences(text, word) {
  const needle = String(word || '').trim().toLowerCase();
  if (!needle) return 0;
  return String(text || '').toLowerCase().split(needle).length - 1;
}

function longParagraphs(content, maxChars) {
  return String(content || '')
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter((block) => block && !NON_PARAGRAPH.test(block))
    .filter((block) => block.length > maxChars);
}

function titleHasKeyword(title, keyword) {
  const squash = (s) => String(s || '').replace(/\s+/g, '').toLowerCase();
  const t = squash(title);
  if (t.includes(squash(keyword))) return true;
  const tokens = String(keyword || '').toLowerCase().split(/\s+/).filter(Boolean);
  return tokens.length > 0 && tokens.every((tok) => t.includes(tok));
}

function validateNaverStructure({ title, content, keyword, tags }) {
  const text = String(content || '');
  const issues = [];
  const h2 = (text.match(/^## /gm) || []).length;
  const keywordCount = countOccurrences(text, keyword);
  const externalLinks = (text.match(/\]\(https?:\/\/[^)]+\)/g) || []).length;
  const codeBlocks = Math.floor((text.match(/^```/gm) || []).length / 2);
  const longOnes = longParagraphs(text, LIMITS.maxParagraphChars);
  const tagCount = Array.isArray(tags) ? tags.length : 0;

  if (text.length < LIMITS.minLength) issues.push(`본문 길이 부족: ${text.length}자 (최소 ${LIMITS.minLength}자)`);
  if (h2 < LIMITS.minH2) issues.push(`소제목(H2) 부족: ${h2}개 (최소 ${LIMITS.minH2}개)`);
  if (!titleHasKeyword(title, keyword)) issues.push('제목에 키워드 없음');
  if (keywordCount < LIMITS.minKeywordCount) issues.push('본문에 키워드 없음');
  if (keywordCount > LIMITS.maxKeywordCount) issues.push(`키워드 반복 과다: ${keywordCount}회 (최대 ${LIMITS.maxKeywordCount}회)`);
  if (externalLinks > LIMITS.maxExternalLinks) issues.push(`외부 링크 과다: ${externalLinks}개 (최대 ${LIMITS.maxExternalLinks}개)`);
  if (codeBlocks > LIMITS.maxCodeBlocks) issues.push(`코드 블록 과다: ${codeBlocks}개 (최대 ${LIMITS.maxCodeBlocks}개)`);
  if (longOnes.length > 0) issues.push(`긴 문단 ${longOnes.length}개 (문단당 최대 ${LIMITS.maxParagraphChars}자)`);
  if (tagCount < LIMITS.minTags || tagCount > LIMITS.maxTags) issues.push(`태그 수 ${tagCount}개 (${LIMITS.minTags}~${LIMITS.maxTags}개)`);

  return {
    passed: issues.length === 0,
    issues,
    stats: {
      length: text.length, h2, keyword_count: keywordCount, external_links: externalLinks,
      code_blocks: codeBlocks, long_paragraphs: longOnes.length, tags: tagCount,
    },
  };
}

if (typeof $input === 'undefined') {
  module.exports = { LIMITS, countOccurrences, longParagraphs, titleHasKeyword, validateNaverStructure };
  return;
}

const item = $input.item.json;
return {
  json: {
    ...item,
    structure_validation: validateNaverStructure({
      title: item.title,
      content: item.content,
      keyword: $('Route Prompt (A/B/C)').item.json.keyword || '',
      tags: item.tags,
    }),
  },
};
````

- [ ] **Step 6: `build_verify_request_naver.js` 작성**

```javascript
/**
 * Build Verify Request (네이버판) — 검증 프롬프트 + 상위 글 + 본문
 * Mode: runOnceForEachItem
 * VERIFY_PROMPT는 scripts/build_naver_workflow.py가 n8n/prompts/prompt_naver_h_verification.md로 채운다.
 */

const VERIFY_PROMPT = /*INJECT:VERIFY_PROMPT*/ 'VERIFY_PROMPT' /*END:VERIFY_PROMPT*/;

function buildVerifyMessage({ keyword, title, content, topPosts }) {
  const tops = (topPosts || []).map((p, i) => `${i + 1}. ${p.title} — ${p.description}`).join('\n');
  return `키워드: ${keyword}\n\n## 네이버 검색 상위 글\n${tops || '(없음)'}`
    + `\n\n## 검증할 글\n제목: ${title}\n본문:\n${content}`;
}

if (typeof $input === 'undefined') {
  module.exports = { VERIFY_PROMPT, buildVerifyMessage };
  return;
}

const item = $input.item.json;
return {
  json: {
    ...item,
    system_prompt: VERIFY_PROMPT,
    user_message: buildVerifyMessage({
      keyword: $('Route Prompt (A/B/C)').item.json.keyword || '',
      title: item.title || '',
      content: item.content || '',
      topPosts: $('Parse SERP Data').item.json.top_posts || [],
    }),
    _llm_purpose: 'verification',
  },
};
```

- [ ] **Step 7: `parse_verification_naver.js` 작성**

`sanitizeJsonStrings`는 기존 워크플로우의 Parse Verification Result와 같은 로직이다.

```javascript
/**
 * Parse Verification Result (네이버판) — LLM 판정 + 구조 검사 + 검색 결과 유무를 합쳐 통과 여부 결정
 * Mode: runOnceForEachItem
 * 입력: Normalize Response (Verify) 출력 { text } — 앞 노드 필드는 넘어오지 않으므로 $('노드')로 읽는다
 * 출력: verification { passed, quality_score, reason, llm_reason, 항목별 boolean }
 * 네이버 4개 항목은 LLM이 빠뜨리면 false로 본다(기존 티스토리 판정은 true로 봄 — 네이버는 엄격하게).
 */

const BASE_CHECKS = ['is_accurate', 'is_logical', 'is_complete', 'is_useful', 'is_in_depth'];
const NAVER_CHECKS = ['no_fabricated_experience', 'natural_keyword_use', 'has_unique_info', 'mobile_readable'];
const MIN_QUALITY_SCORE = 70;

// JSON 문자열 정리 (제어 문자 + 유효하지 않은 이스케이프 복구)
function sanitizeJsonStrings(str) {
  const VALID_ESCAPES = '"\\/bfnrtu';
  let result = '';
  let inString = false;
  for (let i = 0; i < str.length; i++) {
    const ch = str[i];
    if (inString) {
      if (ch === '\\' && i + 1 < str.length) {
        const next = str[i + 1];
        result += VALID_ESCAPES.includes(next) ? ch + next : '\\\\' + next;
        i++;
        continue;
      }
      if (ch === '"') {
        inString = false;
        result += ch;
        continue;
      }
      const code = ch.charCodeAt(0);
      if (code <= 0x1f) {
        if (code === 0x0a) result += '\\n';
        else if (code === 0x0d) result += '\\r';
        else if (code === 0x09) result += '\\t';
        continue;
      }
      result += ch;
    } else {
      if (ch === '"') inString = true;
      result += ch;
    }
  }
  return result;
}

function parseLlmJson(raw) {
  const match = String(raw || '').match(/\{[\s\S]*\}/);
  if (!match) throw new Error('JSON 없음');
  const cleaned = sanitizeJsonStrings(match[0]).replace(/,\s*([}\]])/g, '$1');
  return JSON.parse(cleaned);
}

function judgeNaver(result, { structurePassed, structureIssues, searchOk }) {
  const reasons = [];
  if (!searchOk) reasons.push('네이버 검색 결과 0건');
  if (!structurePassed) reasons.push(`구조 검사 실패: ${(structureIssues || []).join(', ')}`);
  const failed = [...BASE_CHECKS, ...NAVER_CHECKS].filter((key) => result[key] !== true);
  if (failed.length) reasons.push(`검증 미통과: ${failed.join(', ')}`);
  const score = typeof result.quality_score === 'number' ? result.quality_score : 0;
  if (score < MIN_QUALITY_SCORE) reasons.push(`품질 점수 ${score}점 (최소 ${MIN_QUALITY_SCORE})`);

  const checks = Object.fromEntries([...BASE_CHECKS, ...NAVER_CHECKS].map((k) => [k, result[k] === true]));
  return {
    passed: reasons.length === 0,
    quality_score: score,
    reason: reasons.length ? reasons.join(' / ').slice(0, 300) : (result.reason || ''),
    llm_reason: result.reason || '',
    ...checks,
  };
}

if (typeof $input === 'undefined') {
  module.exports = { parseLlmJson, judgeNaver, BASE_CHECKS, NAVER_CHECKS };
  return;
}

let result;
try {
  result = parseLlmJson($input.item.json.text);
} catch (e) {
  result = { quality_score: 0, reason: `LLM 응답 파싱 실패: ${e.message}` };
}
const structure = $('Validate Structure').item.json.structure_validation
  || { passed: false, issues: ['구조 검사 결과 없음'] };

return {
  json: {
    ...$input.item.json,
    verification: judgeNaver(result, {
      structurePassed: structure.passed === true,
      structureIssues: structure.issues || [],
      searchOk: $('Parse SERP Data').item.json.search_ok === true,
    }),
  },
};
```

- [ ] **Step 8: `check_duplicate_naver.js` 작성**

```javascript
/**
 * Check Duplicate (네이버판) — 티스토리·네이버 두 탭의 발행 키워드와 모두 비교
 * Mode: runOnceForAllItems
 * 키워드 출처는 달라도 분야가 같아 주제가 겹칠 수 있다(설계 문서 3.4).
 */

const OVERLAP_THRESHOLD = 0.7;

function keywordOverlap(kwA, kwB) {
  const tokensA = new Set(kwA.toLowerCase().split(/\s+/).filter((t) => t.length > 0));
  const tokensB = new Set(kwB.toLowerCase().split(/\s+/).filter((t) => t.length > 0));
  // 단일 토큰 키워드: 정확 일치만 판정
  if (tokensA.size < 2 || tokensB.size < 2) {
    return kwA.toLowerCase().trim() === kwB.toLowerCase().trim() ? 1.0 : 0;
  }
  const intersection = [...tokensA].filter((t) => tokensB.has(t));
  const smaller = Math.min(tokensA.size, tokensB.size);
  return smaller > 0 ? intersection.length / smaller : 0;
}

function findDuplicate(keyword, existingKeywords, threshold = OVERLAP_THRESHOLD) {
  let maxOverlap = 0;
  let duplicateOf = '';
  for (const existing of existingKeywords) {
    const overlap = keywordOverlap(keyword, existing);
    if (overlap > maxOverlap) {
      maxOverlap = overlap;
      duplicateOf = existing;
    }
  }
  const isDuplicate = maxOverlap >= threshold;
  return {
    is_duplicate: isDuplicate,
    duplicate_of: isDuplicate ? duplicateOf : '',
    max_overlap: Math.round(maxOverlap * 100) / 100,
    threshold,
  };
}

if (typeof $input === 'undefined') {
  module.exports = { keywordOverlap, findDuplicate };
  return;
}

const keywordsOf = (nodeName) => $(nodeName).all()
  .map((item) => item.json['키워드'] || '')
  .filter((kw) => kw.length > 0);
const existing = [
  ...keywordsOf('Sheets Read (Published Keywords)'),  // 티스토리 탭
  ...keywordsOf('Sheets Read (Naver Published)'),     // 네이버 탭
];

return $input.all().map((item) => ({
  json: { ...item.json, duplicate_check: findDuplicate(item.json['키워드'] || '', existing) },
}));
```

- [ ] **Step 9: 테스트 통과 확인**

Run: `node --test "n8n/code_nodes/naver/tests/*.test.js"`
Expected: 모든 테스트 PASS. `구조 검사: 좋은 글은 통과`가 실패하면 테스트의 `goodContent`가 아니라 `LIMITS`와 비교해 어느 규칙이 걸렸는지 `r.issues`를 출력해 확인하고, 규칙이 설계 문서(3.2·3.3)와 맞는 쪽으로 고친다.

- [ ] **Step 10: 커밋**

```bash
git add n8n/code_nodes/naver/
git commit -m "feat(n8n): 네이버 워크플로우 노드 코드와 node 테스트 추가"
```

---

### Task 9: 네이버 워크플로우 생성 스크립트

**Files:**
- Create: `scripts/build_naver_workflow.py`
- Create (생성물): `n8n/workflow_naver.json`
- Test: `tests/unit/scripts/test_build_naver_workflow.py`

**Interfaces:**
- Consumes: Task 7 프롬프트 파일, Task 8 노드 코드 파일과 주입 표식, `n8n/workflow_complete.json`의 노드 이름(`SerpAPI Search`, `Inject Images`, `Parse JSON Response`, `Validate Structure`, `Reduce to Trigger`, `Sheets Read (Published Keywords)`, `Sheets Read (Brain Terms)`, `Schedule Trigger (01:00 AM)`, `Sheets Update (발행대기)` 등)
- Produces: `build() -> dict`, `render(workflow: dict) -> str`, `main(argv: list[str] | None = None) -> int` (`--check`: 커밋된 파일이 최신이면 0, 아니면 1)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/scripts/test_build_naver_workflow.py`:

```python
"""네이버 워크플로우 생성 스크립트 — 티스토리 워크플로우를 복사해 네이버용으로 바꾼다."""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "build_naver_workflow.py"
_spec = importlib.util.spec_from_file_location("build_naver_workflow", _SCRIPT)
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)


@pytest.fixture(scope="module")
def wf() -> dict:
    return builder.build()


def _node(wf: dict, name: str) -> dict:
    matches = [n for n in wf["nodes"] if n["name"] == name]
    assert matches, f"노드 없음: {name}"
    return matches[0]


def _targets(wf: dict, source: str) -> list[str]:
    return [link["node"] for branch in wf["connections"][source]["main"] for link in branch]


def test_네이버_탭을_쓰는_노드(wf):
    for name in builder.TAB_NODES + ["Sheets Read (Naver Published)"]:
        assert _node(wf, name)["parameters"]["sheetName"]["value"] == "naver_calendar"


def test_티스토리_발행_키워드는_티스토리_탭에서_읽는다(wf):
    assert _node(wf, "Sheets Read (Published Keywords)")["parameters"]["sheetName"]["value"] == "gid=0"


def test_serpapi_대신_네이버_검색(wf):
    names = {n["name"] for n in wf["nodes"]}
    assert "SerpAPI Search" not in names
    node = _node(wf, "Naver Blog Search")
    assert node["parameters"]["url"] == "https://openapi.naver.com/v1/search/blog.json"
    assert node["retryOnFail"] is True and node["maxTries"] == 3
    assert "httpCustomAuth" in node["credentials"]


def test_이미지_주입_노드는_없다(wf):
    assert "Inject Images" not in {n["name"] for n in wf["nodes"]}
    assert _targets(wf, "Parse JSON Response") == ["Validate Structure"]
    mapping = _node(wf, "Sheets Update (발행대기)")["parameters"]["columns"]["value"]
    assert "썸네일URL" not in mapping


def test_연결이_모두_존재하는_노드를_가리킨다(wf):
    names = {n["name"] for n in wf["nodes"]}
    for source, outputs in wf["connections"].items():
        assert source in names, source
        for branch in outputs["main"]:
            for link in branch:
                assert link["node"] in names, f"{source} → {link['node']}"


def test_네이버_발행_키워드_조회가_직렬로_끼어든다(wf):
    assert _targets(wf, "Reduce to Trigger") == ["Sheets Read (Naver Published)"]
    assert _targets(wf, "Sheets Read (Naver Published)") == ["Reduce Naver Published"]
    assert _targets(wf, "Reduce Naver Published") == ["Sheets Read (Brain Terms)"]
    # 네이버 탭에 발행 글이 0건이어도 뒤 노드가 실행되게
    assert _node(wf, "Sheets Read (Naver Published)")["alwaysOutputData"] is True


def test_프롬프트가_주입된다(wf):
    route = _node(wf, "Route Prompt (A/B/C)")["parameters"]["jsCode"]
    assert "경험을 지어내지 않습니다" in route
    assert "유형 F: 도구 비교" in route
    assert "'PROMPT_E'" not in route
    verify = _node(wf, "Build Verify Request")["parameters"]["jsCode"]
    assert "no_fabricated_experience" in verify
    assert "'VERIFY_PROMPT' /*END" not in verify


def test_스케줄은_02시_비활성(wf):
    trigger = _node(wf, "Schedule Trigger (02:00 AM)")
    assert trigger["parameters"]["rule"]["interval"][0]["expression"] == "0 2 * * *"
    assert wf["active"] is False


def test_커밋된_파일이_최신이다():
    assert builder.main(["--check"]) == 0


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_주입된_코드가_문법상_유효하다(wf, tmp_path):
    for name in builder.CODE_REPLACEMENTS:
        path = tmp_path / "node.js"
        path.write_text(_node(wf, name)["parameters"]["jsCode"], encoding="utf-8")
        result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, f"{name}: {result.stderr}"
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/unit/scripts/test_build_naver_workflow.py -v`
Expected: FAIL — `FileNotFoundError` (스크립트 없음)

- [ ] **Step 3: 스크립트 작성**

`scripts/build_naver_workflow.py`:

```python
"""n8n/workflow_complete.json(티스토리) → n8n/workflow_naver.json(네이버) 생성.

네이버 워크플로우를 손으로 복사·수정하지 않는다. 노드 코드는 n8n/code_nodes/naver/*.js,
프롬프트는 n8n/prompts/prompt_naver_*.md 가 원본이고 이 스크립트가 JSON에 넣는다.
jsCode를 손으로 붙여넣다 줄바꿈이 이중 이스케이프되는 사고(CLAUDE.md)를 막기 위해서다.

    python scripts/build_naver_workflow.py          # 생성
    python scripts/build_naver_workflow.py --check  # 커밋된 파일이 최신인지 (다르면 종료코드 1)
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N8N_DIR = ROOT / "n8n"
BASE = N8N_DIR / "workflow_complete.json"
OUTPUT = N8N_DIR / "workflow_naver.json"
CODE_DIR = N8N_DIR / "code_nodes" / "naver"
PROMPT_DIR = N8N_DIR / "prompts"

NAVER_TAB = "naver_calendar"
WORKFLOW_NAME = "Blog Automation Pipeline A — Naver"
OLD_TRIGGER = "Schedule Trigger (01:00 AM)"
NEW_TRIGGER = "Schedule Trigger (02:00 AM)"
SCHEDULE_CRON = "0 2 * * *"  # 티스토리(01:00)와 LLM 호출 시간이 겹치지 않게

TAB_NODES = [
    "Sheets Read (Status=대기)",
    "Sheets Update (발행대기)",
    "Sheets Update (검수필요)",
    "Sheets Update (중복스킵)",
]
CODE_REPLACEMENTS = {
    "Parse SERP Data": "parse_naver_search.js",
    "Route Prompt (A/B/C)": "route_prompt_naver.js",
    "Validate Structure": "validate_structure_naver.js",
    "Build Verify Request": "build_verify_request_naver.js",
    "Parse Verification Result": "parse_verification_naver.js",
    "Check Duplicate": "check_duplicate_naver.js",
}
PROMPT_FILES = {
    "E": "prompt_naver_e_howto.md",
    "F": "prompt_naver_f_compare.md",
    "G": "prompt_naver_g_explain.md",
}
COMMON_PROMPT = "prompt_naver_common.md"
VERIFY_PROMPT = "prompt_naver_h_verification.md"

REDUCE_NAVER_CODE = (
    "// 네이버 발행 키워드 N건을 1건으로 축약 — 뒤 노드가 N번 실행되지 않게 한다.\n"
    "// 키워드는 Check Duplicate에서 $('Sheets Read (Naver Published)')로 참조한다.\n"
    "return [{ json: { naver_published_loaded: $input.all().length } }];"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _node(wf: dict, name: str) -> dict:
    for node in wf["nodes"]:
        if node["name"] == name:
            return node
    raise KeyError(f"워크플로우에 노드 없음: {name}")


def _link(name: str) -> dict:
    return {"node": name, "type": "main", "index": 0}


def _rename(wf: dict, old: str, new: str) -> None:
    _node(wf, old)["name"] = new
    conns = wf["connections"]
    if old in conns:
        conns[new] = conns.pop(old)
    for outputs in conns.values():
        for branch in outputs.get("main", []):
            for link in branch:
                if link["node"] == old:
                    link["node"] = new


def _inject(code: str, marker: str, value: object) -> str:
    pattern = re.compile(rf"/\*INJECT:{marker}\*/.*?/\*END:{marker}\*/", re.S)
    if not pattern.search(code):
        raise ValueError(f"주입 표식 없음: {marker}")
    literal = json.dumps(value, ensure_ascii=False)
    return pattern.sub(lambda _: f"/*INJECT:{marker}*/ {literal} /*END:{marker}*/", code)


def _prompts() -> dict[str, str]:
    common = _read(PROMPT_DIR / COMMON_PROMPT).strip()
    return {
        key: f"{common}\n\n{_read(PROMPT_DIR / name).strip()}"
        for key, name in PROMPT_FILES.items()
    }


def _node_code(filename: str) -> str:
    code = _read(CODE_DIR / filename)
    if filename == "route_prompt_naver.js":
        code = _inject(code, "PROMPTS", _prompts())
    if filename == "build_verify_request_naver.js":
        code = _inject(code, "VERIFY_PROMPT", _read(PROMPT_DIR / VERIFY_PROMPT).strip())
    return code


def _use_naver_tab(node: dict) -> None:
    node["parameters"]["sheetName"] = {"__rl": True, "value": NAVER_TAB, "mode": "name"}


def _replace_serp_with_naver_search(wf: dict) -> None:
    _rename(wf, "SerpAPI Search", "Naver Blog Search")
    node = _node(wf, "Naver Blog Search")
    node["id"] = "naver-blog-search"
    node["parameters"] = {
        "method": "GET",
        "url": "https://openapi.naver.com/v1/search/blog.json",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpCustomAuth",
        "sendQuery": True,
        "queryParameters": {"parameters": [
            {"name": "query", "value": "={{ $json['키워드'] }}"},
            {"name": "display", "value": "5"},
            {"name": "sort", "value": "sim"},
        ]},
        "options": {},
    }
    # 두 헤더(X-Naver-Client-Id/Secret)가 필요해 Header Auth 대신 Custom Auth를 쓴다.
    # 키를 $env로 넣으면 실행 기록에 평문으로 남는다.
    node["credentials"] = {
        "httpCustomAuth": {"id": "naverSearchCustomAuth01", "name": "Naver Search API (Custom Auth)"},
    }
    node["retryOnFail"] = True
    node["maxTries"] = 3
    node["waitBetweenTries"] = 2000


def _drop_image_injection(wf: dict) -> None:
    # 외부 이미지 URL 붙여넣기가 네이버에 업로드되는지 검증 전 — 1단계는 텍스트 글(설계 3.5)
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] != "Inject Images"]
    wf["connections"].pop("Inject Images", None)
    wf["connections"]["Parse JSON Response"] = {"main": [[_link("Validate Structure")]]}
    _node(wf, "Sheets Update (발행대기)")["parameters"]["columns"]["value"].pop("썸네일URL", None)


def _add_naver_published_read(wf: dict) -> None:
    tistory_read = _node(wf, "Sheets Read (Published Keywords)")
    naver_read = copy.deepcopy(tistory_read)
    naver_read["name"] = "Sheets Read (Naver Published)"
    naver_read["id"] = "naver-published-read"
    naver_read["alwaysOutputData"] = True  # 네이버 발행 글이 0건이어도 흐름을 잇는다
    naver_read["position"] = [tistory_read["position"][0], tistory_read["position"][1] + 440]
    _use_naver_tab(naver_read)

    reduce_node = copy.deepcopy(_node(wf, "Reduce to Trigger"))
    reduce_node["name"] = "Reduce Naver Published"
    reduce_node["id"] = "reduce-naver-published"
    reduce_node["parameters"]["jsCode"] = REDUCE_NAVER_CODE
    reduce_node["position"] = [reduce_node["position"][0], reduce_node["position"][1] + 440]

    wf["nodes"] += [naver_read, reduce_node]
    # n8n은 병렬 브랜치 순서를 보장하지 않으므로 직렬로 끼운다 (CLAUDE.md)
    conns = wf["connections"]
    conns["Reduce to Trigger"] = {"main": [[_link("Sheets Read (Naver Published)")]]}
    conns["Sheets Read (Naver Published)"] = {"main": [[_link("Reduce Naver Published")]]}
    conns["Reduce Naver Published"] = {"main": [[_link("Sheets Read (Brain Terms)")]]}


def build() -> dict:
    wf = json.loads(_read(BASE))
    for name in TAB_NODES:
        _use_naver_tab(_node(wf, name))
    _replace_serp_with_naver_search(wf)
    _drop_image_injection(wf)
    _add_naver_published_read(wf)
    for name, filename in CODE_REPLACEMENTS.items():
        _node(wf, name)["parameters"]["jsCode"] = _node_code(filename)
    _rename(wf, OLD_TRIGGER, NEW_TRIGGER)
    _node(wf, NEW_TRIGGER)["parameters"]["rule"] = {
        "interval": [{"field": "cronExpression", "expression": SCHEDULE_CRON}],
    }
    return {
        "name": WORKFLOW_NAME,
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings") or {},
        "pinData": {},
        "meta": wf.get("meta") or {},
        "active": False,  # 가져온 뒤 수동 실행으로 검증하고 사람이 켠다
        "tags": [],
    }


def render(workflow: dict) -> str:
    return json.dumps(workflow, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="네이버 n8n 워크플로우 생성")
    parser.add_argument("--check", action="store_true", help="커밋된 파일이 최신인지 확인만")
    args = parser.parse_args(argv)

    text = render(build())
    if args.check:
        if not OUTPUT.exists() or _read(OUTPUT) != text:
            print("n8n/workflow_naver.json이 최신이 아님 — python scripts/build_naver_workflow.py 실행")
            return 1
        print("n8n/workflow_naver.json 최신")
        return 0
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"생성: {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 워크플로우 생성**

Run: `python scripts/build_naver_workflow.py`
Expected: `생성: n8n/workflow_naver.json`

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/unit/scripts/test_build_naver_workflow.py -v && ruff check scripts/build_naver_workflow.py tests/unit/scripts/`
Expected: 모두 PASS, ruff 0건.
`test_주입된_코드가_문법상_유효하다`가 실패하면 stderr의 줄 번호로 주입 결과를 확인한다. 흔한 원인은 프롬프트 안의 백틱이 아니라(json.dumps가 큰따옴표 문자열로 감싸므로 안전) 노드 코드 원본의 문법 오류다.

- [ ] **Step 6: 커밋**

```bash
git add scripts/build_naver_workflow.py n8n/workflow_naver.json tests/unit/scripts/test_build_naver_workflow.py
git commit -m "feat(n8n): 티스토리 워크플로우에서 네이버 워크플로우를 생성하는 스크립트"
```

---

### Task 10: 품질 게이트와 문서

**Files:**
- Modify: `Makefile`
- Modify: `CLAUDE.md` (blog-automation)
- Modify: `docs/superpowers/specs/2026-09-23-naver-blog-pipeline-design.md`

- [ ] **Step 1: Makefile에 `test-n8n` 추가**

1행 `.PHONY`에 `test-n8n`을 추가하고, `test-unit` 타깃 아래에 추가한다:

```makefile
# n8n 네이버 노드 순수 함수 테스트 + 생성된 워크플로우가 최신인지
test-n8n:
	node --test "n8n/code_nodes/naver/tests/*.test.js"
	python scripts/build_naver_workflow.py --check
```

51행 `quality:` 의존 목록 끝에 ` test-n8n`을 붙인다:

```makefile
quality: test-unit coverage lint typecheck validate-ddd test-n8n
```

Run: `make test-n8n`
Expected: node 테스트 전부 pass, `n8n/workflow_naver.json 최신`

- [ ] **Step 2: CLAUDE.md에 네이버 절 추가**

`### 관리자 대시보드` 절의 마지막 줄(`- launchd에 등록하지 않음 — 필요할 때 직접 실행`) 아래에 추가:

```markdown
### 네이버 블로그 (`--platform naver`)

- 흐름: `naver_calendar` 탭 '대기' → n8n `workflow_naver.json`(02:00) → '발행대기' → `python -m src.interface.web --platform naver`에서 사람이 1건씩 발행. 자동 발행 없음, 하루 1건
- **워크플로우 JSON은 손으로 고치지 않는다**: 노드 코드는 `n8n/code_nodes/naver/*.js`, 프롬프트는 `n8n/prompts/prompt_naver_*.md`가 원본이고 `python scripts/build_naver_workflow.py`가 `workflow_complete.json`을 복사해 넣는다. 원본을 고친 뒤 스크립트를 돌려 n8n에 다시 가져올 것. `make test-n8n`이 최신 여부를 검사한다
- 로그인은 사람이 한다: `python scripts/naver_blog.py login`('로그인 상태 유지' 체크), 세션은 `.browser_data_naver/`. `NAVER_BLOG_ID`는 로그인 아이디가 아니라 블로그 주소(`sangpedia`)
- SmartEditor 실측(2026-09-23): 진입은 `?Redirect=Write`(`/postwrite`는 홈으로 튕길 때가 있음), 제목·본문 입력은 숨은 `input_buffer*` iframe으로 간다. 셀렉터는 `naver/selectors.py` 한 곳
- 발행 확인 뒤 URL을 못 받으면 사유에 "발행 여부 수동 확인 필요"가 남는다 — 네이버에서 직접 확인 전에는 다시 발행하지 말 것(중복 발행)
- 네이버 검색 API 키는 n8n 자격증명 `Naver Search API (Custom Auth)`에 둔다(`{"headers": {"X-Naver-Client-Id": ..., "X-Naver-Client-Secret": ...}}`)
```

- [ ] **Step 3: 설계 문서를 구현에 맞게 고친다**

`docs/superpowers/specs/2026-09-23-naver-blog-pipeline-design.md`에서:

1. 3.1 표 위 문장 `(`n8n/prompts/`, 기존 a~d는 수정하지 않음)` 아래에 한 줄 추가:
   `공통 규칙은 `prompt_naver_common.md`에 두고 각 유형 파일 앞에 붙인다.`
2. 3.1의 라우팅 문장을 다음으로 바꾼다:
   `` `route_prompt`는 키워드 패턴으로 고른다. `vs`·`비교`·`차이`는 f, `란`·`이란`·`뜻`·`개념`·`쉽게`로 끝나는 키워드나 AI-Brain 용어와 **정확히 일치**하는 키워드는 g, 나머지는 e. 부분 일치로 정하면 'AI' 같은 짧은 용어가 대부분의 키워드를 g로 끌고 간다. ``
3. 3.3의 1번 끝 문장 `아래 항목을 어기면 LLM 검증 없이 `검수필요`로 기록한다.`를 다음으로 바꾼다:
   `아래 항목을 어기면 LLM 점수와 무관하게 `검수필요`로 기록한다 (판정은 Parse Verification Result에서 합친다 — n8n에 분기 노드를 늘리지 않으려고 LLM 검증 호출은 그대로 한다).`
4. 4장 표의 `네이버 검색 API 실패 (n8n)` 행을 다음으로 바꾼다:
   `| 네이버 검색 API 실패 (n8n) | HTTP 노드가 3회 시도한다. 그래도 실패하면 실행이 오류로 멈추고 행은 `대기`로 남아 다음 날 다시 시도한다. 검색 결과가 0건이면 생성은 하되 `검수필요`로 기록한다 |`
5. 2장 흐름도의 `[n8n] workflow_naver.json (매일 1회)`를 `[n8n] workflow_naver.json (매일 02:00, 티스토리 01:00과 분리)`로 바꾼다
6. 4장 표의 `네이버 세션 만료` 행을 다음으로 바꾼다 (대시보드는 사람이 화면 앞에 있으므로 예외·텔레그램 대신 작업 결과로 보여 준다 — 기존 수동 발행과 같은 방식):
   `| 네이버 세션 만료 | 대시보드 작업 결과가 "로그인 실패 — 발행대기 유지"로 끝나고 글 상태는 바뀌지 않는다. 로그(`logs/dashboard-web.log`)에 `scripts/naver_blog.py login` 재실행 안내가 남는다. `NAVER_BLOG_ID`가 블로그 주소와 다르면 로그인 확인 단계에서 원인을 적은 예외가 난다 |`

- [ ] **Step 4: 전체 품질 게이트**

Run: `make quality`
Expected: `✅ ALL QUALITY GATES PASSED`. `validate-ddd`가 Xcode 라이선스 문제로 실행되지 않으면
`grep -rn "src\.infrastructure\|src\.application" src/domain | wc -l`(0이어야 함)과
`grep -rn "src\.application" src/infrastructure | wc -l`(0이어야 함)로 대신 확인하고 그 사실을 보고한다.
mypy는 작업 전부터 있던 오류(15건)가 있어 `make typecheck`가 실패할 수 있다 — 새로 늘어난 오류가 없는지만 확인하고 보고한다.

- [ ] **Step 5: 커밋**

```bash
git add Makefile CLAUDE.md docs/superpowers/specs/2026-09-23-naver-blog-pipeline-design.md
git commit -m "docs: 네이버 파이프라인 운영 규칙과 test-n8n 품질 게이트"
```

---

### Task 11: 실측 E2E (사람 + Claude)

자동화할 수 없는 단계다. 사용자 작업과 Claude 작업을 구분해 순서대로 진행한다.

- [ ] **Step 1 (사용자): 네이버 검색 API 발급과 n8n 자격증명**
  - developers.naver.com → 애플리케이션 등록 → 사용 API "검색" → Client ID/Secret 발급
  - n8n(localhost:5678) → Credentials → New → "Custom Auth" → 이름 `Naver Search API (Custom Auth)`, 값:
    `{"headers": {"X-Naver-Client-Id": "<ID>", "X-Naver-Client-Secret": "<SECRET>"}}`

- [ ] **Step 2 (사용자): 시트 탭 준비**
  - `keyword_calendar_v2`에 `naver_calendar` 탭을 추가하고 1행 헤더를 첫 탭에서 그대로 복사
  - 시험 키워드 3행 입력(상태 `대기`): `노션 AI 사용법`, `Claude vs ChatGPT 업무용`, `MCP란`

- [ ] **Step 3 (사용자): 워크플로우 가져오기**
  - n8n → Import from File → `n8n/workflow_naver.json`
  - `Naver Blog Search` 노드의 자격증명을 Step 1 것으로 선택, Google/Gemini 자격증명이 연결됐는지 확인
  - 비활성 상태로 두고 `Manual Trigger (Test)`로 1회 실행

- [ ] **Step 4 (Claude): 생성 결과 확인**

```bash
python - <<'EOF'
from dotenv import load_dotenv; load_dotenv()
from src.infrastructure.config import Config
from src.infrastructure.persistence.google_sheets_repo import GoogleSheetsPostRepository
c = Config.from_env()
repo = GoogleSheetsPostRepository(c.google_creds, c.sheet_name, worksheet=c.naver_sheet_tab)
for p in repo.find_all():
    body = (p.content.body_markdown or "") if p.content else ""
    print(p.row_index, p.keyword, p.status.value, p.quality_score, len(body), (p.error_message or "")[:120])
EOF
```

Expected: 3행 모두 `발행대기`(품질 70점 이상, 본문 3,000자 이상) 또는 `검수필요`(사유 기록). `보류`(HOLD)로 읽히는 `검수필요`·`중복스킵`은 정상이다. 실행이 멈췄으면 n8n 실행 기록에서 LLM 노드의 `finishReason`을 확인한다(CLAUDE.md "LLM 토큰 예산").
검수필요가 3건 모두면 사유를 모아 프롬프트(Task 7) 또는 `LIMITS`(Task 8)를 조정하고 Task 9 스크립트를 다시 돌린 뒤 재실행한다.

- [ ] **Step 5 (사용자 승인 후 Claude 또는 사용자): 1건 공개 발행**
  - `python -m src.interface.web --platform naver` → 로그인 → 상단 이름이 "네이버 블로그 관리자"인지 확인 → 발행대기 1건 발행
  - 확인: 시트의 해당 행이 `발행완료`, `published_url`이 `https://blog.naver.com/sangpedia/<숫자>`, `entry_id`가 그 숫자. 공개 글에서 제목·소제목·표·목록·태그가 보이는지
  - 실패 시 `logs/naver/*.png`와 `logs/dashboard-web.log`를 본다. 사유가 "발행 여부 수동 확인 필요"면 네이버 블로그에서 글이 올라갔는지 먼저 확인하고, 올라갔으면 시트에 URL을 직접 적는다

- [ ] **Step 6 (Claude): 메모리 갱신**

`memory/naver-pipeline-in-progress.md`에 E2E 결과(성공 여부, 조정한 규칙)를 반영하고, 완료됐으면 "진행 중" 메모리를 지우고 재조사 불필요 결론만 남긴다.
