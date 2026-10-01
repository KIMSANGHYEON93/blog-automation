# 통합 관리자 페이지(hub) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버·티스토리 대시보드를 한 프로세스·한 주소(8787)·한 번 로그인으로 묶고, 상단 탭으로 전환한다.

**Architecture:** 기존 `create_app`으로 플랫폼별 Flask 앱 두 개를 만들고 werkzeug `DispatcherMiddleware`로 `/naver`·`/tistory`에 마운트한다. 두 앱은 같은 시크릿·쿠키 경로 `/`로 세션(로그인·CSRF)을 공유하고, `LoginThrottle` 인스턴스 하나를 같이 받는다. 단독 실행(`--platform`)은 그대로 남긴다.

**Tech Stack:** Python 3.9 타깃, Flask, werkzeug(`DispatcherMiddleware`, `run_simple`, `werkzeug.test.Client`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-01-dashboard-hub-design.md`

## Global Constraints

- 모든 작업은 워크트리 `/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation/.claude/worktrees/naver-pipeline` 안에서만 한다. 운영 폴더(`/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation/` 바로 아래)의 파일은 읽기만 하고 절대 쓰지 않는다.
- `.env`는 쓰지 않고, 내용을 출력하거나 보고에 옮기지 않는다(비밀값). launchd(`launchctl`)는 건드리지 않는다 — 전환은 사용자 확인 후 컨트롤러가 한다.
- 새 의존성 추가 금지(werkzeug는 Flask와 함께 이미 설치됨).
- 사용자에게 보이는 문구·로그·주석은 한국어. 탭 문구는 정확히 `네이버`, `티스토리`.
- 탭 주소는 정확히 `/naver/`, `/tistory/`. `/`는 `/naver/`로 302.
- 로그인 시도 제한은 두 앱 합산(같은 `LoginThrottle` 인스턴스).
- 기존 동작 불변: 단독 실행(`python -m src.interface.web [--platform naver]`)에서는 탭이 보이지 않는다.
- 품질: `python -m pytest tests/unit -q` 전부 통과, `ruff check src/ tests/` 0건, mypy는 기준선(16건)에서 늘지 않음.
- 커밋 메시지 형식 `feat(web): …` 등, 본문 끝에 두 줄:
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01FqjKkJHg262ucm1vLLcPUi`

## 파일 구조

| 파일 | 역할 |
|------|------|
| `src/interface/web/app.py` (수정) | `create_app(hub_tab=...)`, `HUB_TABS`, 쿠키 경로 `/` |
| `src/interface/web/templates/base.html` (수정) | 탭 렌더링 |
| `src/interface/web/static/dashboard.css` (수정) | 탭 스타일 |
| `src/interface/web/hub.py` (생성) | `build_hub(apps)` — 마운트 + `/` 리다이렉트 |
| `src/interface/web/__main__.py` (수정) | `_build_app` 분리, `hub` 명령 |
| `scripts/com.blog-automation.dashboard-hub.plist` (생성) | 상시 실행 |
| `CLAUDE.md` (수정) | 대시보드 항목 갱신 |
| `tests/unit/interface/test_web_app.py` (수정) | 탭·쿠키 경로 테스트 |
| `tests/unit/interface/test_web_hub.py` (생성) | 마운트·세션 공유·제한 합산 테스트 |

---

### Task 1: 앱에 탭 표시와 공유 쿠키 경로

**Files:**
- Modify: `src/interface/web/app.py` (`JOB_LABELS` 아래 상수, `create_app` 시그니처·`app.config.update`·globals)
- Modify: `src/interface/web/templates/base.html` (header 안)
- Modify: `src/interface/web/static/dashboard.css` (`.topbar nav` 근처 + `@media (max-width: 640px)` 블록)
- Test: `tests/unit/interface/test_web_app.py`

**Interfaces:**
- Produces: `create_app(..., hub_tab: str | None = None)` — `"naver"`/`"tistory"`면 로그인 후 탭 표시, `None`이면 숨김, 그 밖의 값은 `ValueError`. 상수 `HUB_TABS: tuple[tuple[str, str, str], ...] = (("naver", "네이버", "/naver/"), ("tistory", "티스토리", "/tistory/"))` — (플랫폼 키, 표시 이름, 마운트 주소).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/interface/test_web_app.py`의 `Harness.__init__`에 `hub_tab=None` 매개변수를 추가하고 `create_app(...)` 호출 끝에 `hub_tab=hub_tab,`를 넘긴다:

```python
class Harness:
    def __init__(self, publish=None, allowed_hosts=None, now=NOON, revise=None, hub_tab=None):
        ...
        app = create_app(
            ...
            clock=lambda: now,
            hub_tab=hub_tab,
        )
```

파일 끝에 추가:

```python
class TestHubTabs:
    def test_단독_실행에는_탭이_없다(self, h):
        h.login()
        assert 'class="tabs"' not in h.client.get("/").get_data(as_text=True)

    def test_통합_실행은_현재_블로그_탭을_강조한다(self):
        h = Harness(hub_tab="tistory")
        h.login()
        html = h.client.get("/").get_data(as_text=True)
        assert '<a href="/naver/">네이버</a>' in html
        assert '<a href="/tistory/" aria-current="page">티스토리</a>' in html

    def test_로그인_전에는_탭이_없다(self):
        h = Harness(hub_tab="naver")
        assert 'class="tabs"' not in h.client.get("/login").get_data(as_text=True)

    def test_모르는_탭은_거부(self):
        with pytest.raises(ValueError):
            Harness(hub_tab="wordpress")

    def test_세션_쿠키는_루트_경로(self, h):
        cookie = h.login().headers["Set-Cookie"]
        assert re.search(r"Path=/(;|$)", cookie), cookie
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/unit/interface/test_web_app.py::TestHubTabs -v`
Expected: FAIL — `create_app() got an unexpected keyword argument 'hub_tab'`

- [ ] **Step 3: 구현**

`src/interface/web/app.py` — `JOB_LABELS` 정의 바로 아래:

```python
# 통합 대시보드(hub) 탭: (플랫폼, 표시 이름, 마운트 주소) — hub.py가 이 주소로 앱을 붙인다
HUB_TABS = (("naver", "네이버", "/naver/"), ("tistory", "티스토리", "/tistory/"))
```

`create_app` 키워드 인자 끝(`clock` 다음)에 `hub_tab: str | None = None,` 추가. 함수 본문의 시크릿 길이 검사 바로 아래:

```python
    if hub_tab is not None and hub_tab not in {key for key, _, _ in HUB_TABS}:
        raise ValueError(f"알 수 없는 탭: {hub_tab}")
```

`app.config.update(...)`에 추가:

```python
        # 통합 대시보드: /naver·/tistory 두 앱이 같은 로그인 세션을 쓴다
        SESSION_COOKIE_PATH="/",
```

`app.jinja_env.globals["daily_limit"] = daily_limit` 줄 아래:

```python
    app.jinja_env.globals["hub_tabs"] = HUB_TABS if hub_tab else ()
    app.jinja_env.globals["hub_tab"] = hub_tab
```

`src/interface/web/templates/base.html` — `<a class="brand" ...>` 줄 바로 아래:

```html
    {% if hub_tabs and session.get('admin') %}
    <nav class="tabs" aria-label="블로그">
      {% for key, label, href in hub_tabs %}<a href="{{ href }}"{% if key == hub_tab %} aria-current="page"{% endif %}>{{ label }}</a>{% endfor %}
    </nav>
    {% endif %}
```

`src/interface/web/static/dashboard.css` — `.topbar nav { ... }` 줄(50행 근처) 아래:

```css
/* 통합 대시보드 블로그 전환 탭(세그먼트 컨트롤) */
.topbar nav.tabs { gap: 2px; padding: 2px; border-radius: 8px; background: var(--fill); }
.tabs a { padding: 5px 14px; border-radius: 6px; font-size: 14px; color: var(--muted); }
.tabs a:hover { text-decoration: none; color: var(--text); }
.tabs a[aria-current="page"] { background: var(--card); color: var(--text); font-weight: 600; box-shadow: var(--shadow); }
```

같은 파일 `@media (max-width: 640px) {` 블록의 첫 줄 `.topbar { padding-left: 16px; }`를 다음 세 줄로 바꾼다(좁은 화면에서는 탭을 둘째 줄 전체 폭으로):

```css
  .topbar { padding: 8px 16px; height: auto; min-height: 52px; flex-wrap: wrap; }
  .topbar nav.tabs { order: 3; width: 100%; }
  .tabs a { flex: 1; text-align: center; padding: 8px 0; }
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/unit/interface/test_web_app.py -q`
Expected: 전부 PASS (기존 테스트 포함)

- [ ] **Step 5: 커밋**

```bash
git add src/interface/web/app.py src/interface/web/templates/base.html src/interface/web/static/dashboard.css tests/unit/interface/test_web_app.py
git commit -m "feat(web): 통합 대시보드용 블로그 전환 탭과 공유 쿠키 경로"
```

---

### Task 2: 두 앱을 한 WSGI로 묶는 hub

**Files:**
- Create: `src/interface/web/hub.py`
- Test: `tests/unit/interface/test_web_hub.py`

**Interfaces:**
- Consumes: Task 1의 `create_app(..., hub_tab=...)`, `HUB_TABS`.
- Produces: `build_hub(apps: Mapping[str, Flask]) -> DispatcherMiddleware` — `apps`의 키 집합은 `HUB_TABS`의 플랫폼 키(`"naver"`, `"tistory"`)와 정확히 같아야 하고, 다르면 `ValueError`. `/naver/...`·`/tistory/...`로 마운트, 그 밖의 경로는 첫 탭 주소(`/naver/`)로 302.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/interface/test_web_hub.py`:

```python
"""통합 대시보드(hub) — 마운트, 세션 공유, 로그인 제한 합산."""
from __future__ import annotations

import re

import pytest
from werkzeug.security import generate_password_hash
from werkzeug.test import Client

from src.application.use_cases.list_posts import ListPostsUseCase
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository
from src.interface.web.app import create_app
from src.interface.web.auth import AdminAuthenticator, LoginThrottle
from src.interface.web.hub import build_hub
from src.interface.web.jobs import PublishJobRunner

PASSWORD = "correct horse battery"


def _app(tab: str, throttle: LoginThrottle):
    app = create_app(
        authenticator=AdminAuthenticator("admin", generate_password_hash(PASSWORD)),
        list_posts=ListPostsUseCase(InMemoryPostRepository([])),
        job_runner=PublishJobRunner(publish=lambda row: None),
        secret_key="test-secret-key-0123456789",
        throttle=throttle,
        brand_label=f"{tab} 관리자",
        hub_tab=tab,
    )
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client() -> Client:
    throttle = LoginThrottle(max_attempts=3, window_seconds=600)
    return Client(build_hub({"naver": _app("naver", throttle), "tistory": _app("tistory", throttle)}))


def _csrf(client: Client, path: str) -> str:
    html = client.get(path).get_data(as_text=True)
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, f"CSRF 토큰 없음: {path}"
    return match.group(1)


def _login(client: Client, prefix: str, password: str = PASSWORD):
    return client.post(f"{prefix}/login", data={
        "username": "admin", "password": password, "csrf_token": _csrf(client, f"{prefix}/login"),
    })


def test_루트는_네이버로(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/naver/")


def test_로그인_전에는_각_앱의_로그인으로(client):
    resp = client.get("/tistory/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/tistory/login")


def test_한_번_로그인으로_두_탭(client):
    assert _login(client, "/naver").status_code == 302
    assert client.get("/naver/").status_code == 200
    assert client.get("/tistory/").status_code == 200


def test_로그아웃도_함께(client):
    _login(client, "/naver")
    client.post("/tistory/logout", data={"csrf_token": _csrf(client, "/tistory/")})
    assert client.get("/naver/").status_code == 302


def test_로그인_실패_제한은_합산(client):
    _login(client, "/naver", password="nope")
    _login(client, "/naver", password="nope")
    _login(client, "/tistory", password="nope")
    assert _login(client, "/tistory").status_code == 429


def test_링크와_폼에_접두어(client):
    _login(client, "/tistory")
    html = client.get("/tistory/").get_data(as_text=True)
    assert 'action="/tistory/logout"' in html
    assert 'href="/tistory/static/dashboard.css' in html
    assert '<a href="/tistory/" aria-current="page">티스토리</a>' in html


def test_탭_키가_다르면_거부():
    with pytest.raises(ValueError):
        build_hub({"naver": _app("naver", LoginThrottle())})
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/unit/interface/test_web_hub.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.interface.web.hub'`

- [ ] **Step 3: 구현**

`src/interface/web/hub.py`:

```python
"""통합 대시보드: 플랫폼별 앱을 /naver·/tistory에 붙인 WSGI 하나.

세션 공유는 각 앱이 같은 시크릿과 쿠키 경로 '/'를 쓰는 것으로 된다(create_app).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Callable

from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.utils import redirect

from src.interface.web.app import HUB_TABS


def build_hub(apps: Mapping[str, Flask]) -> DispatcherMiddleware:
    expected = {key for key, _, _ in HUB_TABS}
    if set(apps) != expected:
        raise ValueError(f"통합 대시보드에는 {sorted(expected)} 앱이 모두 필요합니다")
    home = HUB_TABS[0][2]

    def to_home(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        return redirect(home)(environ, start_response)

    return DispatcherMiddleware(to_home, {href.rstrip("/"): apps[key] for key, _, href in HUB_TABS})
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/unit/interface/test_web_hub.py -v`
Expected: 7 passed. `test_한_번_로그인으로_두_탭`이 실패하면 Task 1의 `SESSION_COOKIE_PATH="/"`가 들어갔는지 확인한다. mypy가 `DispatcherMiddleware` 인자 타입을 지적하면 werkzeug의 `WSGIApplication` 타입(`from _typeshed.wsgi import WSGIApplication`은 `TYPE_CHECKING` 안에서만)으로 맞춘다.

- [ ] **Step 5: 커밋**

```bash
git add src/interface/web/hub.py tests/unit/interface/test_web_hub.py
git commit -m "feat(web): 네이버·티스토리 앱을 한 주소로 묶는 통합 대시보드"
```

---

### Task 3: `hub` 실행 명령, launchd plist, 문서

**Files:**
- Modify: `src/interface/web/__main__.py` (`_serve`를 `_load_settings` + `_build_app` + `_serve`로 분리, `_serve_hub` 추가, `main`에 `hub`)
- Create: `scripts/com.blog-automation.dashboard-hub.plist`
- Modify: `CLAUDE.md` ("관리자 대시보드" 절의 launchd 항목)

**Interfaces:**
- Consumes: `create_app(..., throttle=..., hub_tab=...)`(Task 1), `build_hub`(Task 2).
- Produces: `python -m src.interface.web hub` — 설정의 host:port(기본 127.0.0.1:8787)에서 통합 대시보드 실행.

이 모듈은 Google Sheets·브라우저를 조립하는 Composition Root라 단위 테스트가 없다(기존 `_serve`도 없음). 검증은 Step 4의 스모크 실행으로 한다.

- [ ] **Step 1: `_serve` 분리**

`src/interface/web/__main__.py` import 정리:
- `from src.interface.web.auth import AdminAuthenticator` → `from src.interface.web.auth import AdminAuthenticator, LoginThrottle`
- 추가: `from flask import Flask`, `from werkzeug.serving import run_simple`, `from src.interface.web.hub import build_hub`
- 순서는 `ruff check --fix src/interface/web/__main__.py`로 맞춘다.

기존 `_serve` 함수 전체를 다음 네 함수로 바꾼다. `create_app(...)` 인자는 지금 `_serve` 안의 것과 같고, 늘어난 것은 `throttle=throttle,`과 `hub_tab=hub_tab,` 두 줄뿐이다:

```python
def _load_settings() -> DashboardSettings | None:
    try:
        return DashboardSettings.from_env(os.environ)
    except SettingsError as e:
        print(f"대시보드 설정 오류: {e}", file=sys.stderr)
        return None


def _build_app(
    platform: str, settings: DashboardSettings, throttle: LoginThrottle | None = None,
    hub_tab: str | None = None,
) -> Flask:
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
    return create_app(
        authenticator=AdminAuthenticator(settings.admin_user, settings.admin_password_hash),
        list_posts=ListPostsUseCase(repo),
        job_runner=PublishJobRunner(
            publish=_build_publisher(config, repo, profile),
            draft=_build_drafter(config, repo, profile) if profile.name == "naver" else None,
            revise=_build_reviser(config, repo, profile) if profile.name == "naver" else None,
            login=(
                build_relogin(config, PROJECT_ROOT, DirectoryPipelineLock(LOCK_DIR))
                if profile.name == "naver" else None
            ),
            generate=(
                build_generator(
                    os.getenv("N8N_CONTAINER", DEFAULT_N8N_CONTAINER), NAVER_WORKFLOW_NAME,
                    lambda: _generation_snapshot(repo),
                ) if profile.name == "naver" else None
            ),
        ),
        edit_post=EditPostUseCase(repo),
        preview=(
            (lambda post: build_preview_html(post.keyword, post.body_markdown))
            if profile.name == "naver" else None
        ),
        keywords=_build_keyword_desk(config, repo, profile),
        daily_limit=profile.daily_limit,
        secret_key=settings.secret_key,
        throttle=throttle,
        secure_cookies=settings.secure_cookies,
        allowed_hosts=settings.allowed_hosts,
        brand_label=profile.label,
        hub_tab=hub_tab,
    )


def _serve(platform: str) -> int:
    settings = _load_settings()
    if settings is None:
        return 2
    app = _build_app(platform, settings)
    logger.info(f"대시보드 시작: http://{settings.host}:{settings.port}")
    app.run(host=settings.host, port=settings.port, debug=False, threaded=True, use_reloader=False)
    return 0


def _serve_hub() -> int:
    settings = _load_settings()
    if settings is None:
        return 2
    throttle = LoginThrottle()  # 두 앱 합산 — 따로 두면 실패 허용 횟수가 두 배가 된다
    hub = build_hub({
        name: _build_app(name, settings, throttle, hub_tab=name) for name in ("naver", "tistory")
    })
    logger.info(f"통합 대시보드 시작: http://{settings.host}:{settings.port}/")
    run_simple(settings.host, settings.port, hub, threaded=True, use_reloader=False)
    return 0
```

- [ ] **Step 2: `hub` 명령 연결**

`main()`에서 `choices=["serve", "hash-password", "gen-secret"]`를 `choices=["serve", "hub", "hash-password", "gen-secret"]`로 바꾸고, 마지막 `return _serve(args.platform)`을 다음으로 바꾼다:

```python
    if args.command == "hub":
        return _serve_hub()
    return _serve(args.platform)
```

모듈 docstring 사용법 목록 끝에 한 줄 추가:

```
    python -m src.interface.web hub             # 통합 대시보드 (/naver/ · /tistory/ 탭)
```

- [ ] **Step 3: 단위 테스트·린트**

Run: `python -m pytest tests/unit -q && ruff check src/ tests/ && mypy src/ --ignore-missing-imports 2>&1 | tail -1`
Expected: 테스트 전부 통과, ruff `All checks passed!`, mypy `Found 16 errors` 이하.

- [ ] **Step 4: 스모크 실행 (운영 .env를 읽기만 함, 포트 8790)**

```bash
PROD="/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation"
SMOKE="$(mktemp -d)"
( set -a; . "$PROD/.env"; set +a
  GOOGLE_CREDS="$PROD/credentials.json" SITE_PROFILE="$PROD/site_profile.json" \
  DASHBOARD_PORT=8790 python -m src.interface.web hub > "$SMOKE/hub.log" 2>&1 & echo $! > "$SMOKE/pid" )
sleep 10
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" http://127.0.0.1:8790/
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" http://127.0.0.1:8790/tistory/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8790/naver/login
kill "$(cat "$SMOKE/pid")"; grep -c Traceback "$SMOKE/hub.log"
```

Expected: `302 http://127.0.0.1:8790/naver/`, `302 http://127.0.0.1:8790/tistory/login`, `200`, Traceback 개수 `0`. (`.env`·로그 내용을 출력하거나 커밋하지 않는다. Traceback이 있으면 해당 부분만 비밀값을 가리고 보고한다.)

- [ ] **Step 5: plist 작성**

`scripts/com.blog-automation.dashboard-hub.plist` — `scripts/com.blog-automation.naver-dashboard.plist`를 복사해 다음만 바꾼다:
- 맨 위 주석 첫 줄: `통합 관리자 대시보드(네이버·티스토리 탭) 상시 실행(127.0.0.1:8787, 폰은 tailscale serve로 접속). com.blog-automation.naver-dashboard를 대체한다 — 둘을 동시에 load하면 8787을 다툰다. 설치:` 그리고 설치 명령 두 줄의 파일명을 `com.blog-automation.dashboard-hub.plist`로. PATH 설명 줄은 유지.
- `Label`: `com.blog-automation.dashboard-hub`
- `ProgramArguments`: python 경로, `-m`, `src.interface.web`, `hub` (`--platform`, `naver` 두 줄 삭제)
- `StandardErrorPath`/`StandardOutPath`: `/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation/logs/dashboard_hub.err`, `.../logs/dashboard_hub.log`

확인: `plutil -lint scripts/com.blog-automation.dashboard-hub.plist` → `OK`

- [ ] **Step 6: CLAUDE.md 갱신**

워크트리 `CLAUDE.md`의 "관리자 대시보드" 절에서 `- 네이버 대시보드는 launchd `com.blog-automation.naver-dashboard`(KeepAlive, ...` 로 시작해 `... 티스토리 대시보드는 필요할 때 다른 포트(`DASHBOARD_PORT=8788`)로 직접 실행`으로 끝나는 항목 하나를 다음으로 바꾼다:

```markdown
- 통합 대시보드: launchd `com.blog-automation.dashboard-hub`(KeepAlive, 127.0.0.1:8787, `scripts/`의 plist)가 `python -m src.interface.web hub`로 상시 실행. `/naver/`·`/tistory/` 두 앱(`hub.py`, werkzeug `DispatcherMiddleware`)이 같은 시크릿·쿠키 경로 `/`로 로그인을 공유하고 로그인 제한(`LoginThrottle`)도 합산한다. 상단 탭으로 전환, `/`는 `/naver/`로. 재시작은 `launchctl kickstart -k gui/$(id -u)/com.blog-automation.dashboard-hub` — 8787을 다른 프로세스가 잡고 있으면 KeepAlive가 30초마다 실패를 반복한다. 단독 실행(`--platform`)은 탭 없이 그대로 동작한다. 되돌릴 때는 hub를 unload하고 `com.blog-automation.naver-dashboard` plist를 load
```

- [ ] **Step 7: 커밋**

```bash
git add src/interface/web/__main__.py scripts/com.blog-automation.dashboard-hub.plist CLAUDE.md
git commit -m "feat(web): 통합 대시보드 hub 실행 명령과 launchd plist"
```

---

### 전환 (컨트롤러, 사용자 확인 후 — 서브에이전트 작업 아님)

1. `feat/naver-pipeline` → `master` fast-forward 병합(운영 폴더가 master를 실행)
2. `cp scripts/com.blog-automation.dashboard-hub.plist ~/Library/LaunchAgents/`
3. `launchctl unload ~/Library/LaunchAgents/com.blog-automation.naver-dashboard.plist` → `launchctl load ~/Library/LaunchAgents/com.blog-automation.dashboard-hub.plist`
4. `curl`로 302 확인 후 사용자가 폰(Tailscale 주소)에서 두 탭·로그인·목록 확인
5. 되돌리기: hub unload → naver-dashboard load
