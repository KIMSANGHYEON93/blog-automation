# 네이버 세션 원격 복구 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버 세션이 만료되면 새 텔레그램 봇이 알리고, 폰에서 대시보드 '네이버 다시 로그인' 버튼 → 자동 입력 → 폰 네이버 앱 승인으로 세션을 되살린다.

**Architecture:** 로그인 판정·입력은 새 모듈 `naver/login.py`(순수 판정 함수 + 가짜 브라우저로 시험 가능한 `auto_login`)에 두고, 어댑터 `relogin()`이 브라우저 시작·세션 확인을 감싼다. 대시보드는 기존 `PublishJobRunner`에 작업 종류 `login`을 추가해 인증·CSRF·락·자동 실행 시간 거부·작업 화면을 그대로 재사용한다. 알림은 기존 `TelegramNotificationAdapter`에 새 봇 토큰만 넣는다.

**Tech Stack:** Python 3.9 타깃(3.11 실행), SeleniumBase, Flask, pytest, launchd

**Spec:** `docs/superpowers/specs/2026-09-30-naver-relogin-design.md`

## Global Constraints

- 작업 위치: 워크트리 `/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation/.claude/worktrees/naver-pipeline` (브랜치 `feat/naver-pipeline`). 원 저장소 폴더는 launchd 운영 코드라 건드리지 않는다
- Python 3.9 호환 문법. `X | None`은 파일 첫 줄에 `from __future__ import annotations`가 있을 때만
- ruff line length 100, 규칙 E/F/W/I/N/UP/B/A/SIM. 테스트 함수명 한글 허용
- DDD 계층: Domain은 stdlib만, Application은 Domain만, Infrastructure는 Application import 금지, Interface는 전부 가능
- 로그·사용자 메시지·주석은 한국어
- **비밀번호·아이디를 로그·작업 메시지·예외 문자열·스크린샷에 남기지 않는다**
- **로그인 시도는 버튼 1회에 제출 1회. 자동 재시도 없음**
- 새 봇 토큰 환경변수 `NAVER_TELEGRAM_BOT_TOKEN`, 채팅은 기존 `TELEGRAM_CHAT_ID`, 로그인 값 `NAVER_LOGIN_ID`·`NAVER_LOGIN_PW`
- 폰 승인 대기 최대 300초, 아침 점검 07:30
- `.env`는 수정하지 않는다. `.env.example`만 수정한다. 기존 launchd 스케줄은 바꾸지 않는다
- ponytail 원칙: 기존 코드 재사용이 먼저, 요청받지 않은 추상화 금지
- 커밋 메시지 끝에 다음 두 줄을 그대로 붙인다:
  ```
  Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01FqjKkJHg262ucm1vLLcPUi
  ```
- 이 워크트리 세션에서는 셸 `git log/show/status/diff`가 훅에 막힐 수 있다. 커밋은 `git -C "<워크트리>" add ...`·`git -C "<워크트리>" commit ...`, 확인은 `git cat-file -p <sha>`·`git rev-parse`를 쓴다
- 새 파일을 처음 만들거나 고칠 때 GateGuard 훅이 한 번 거부하고 사실 제시를 요구한다. 거부되면 ① 이 파일을 부르는 곳 ② 영향받는 공개 API ③ 데이터 스키마 ④ 사용자 지시 원문("ㄱ" — 승인된 구현 계획 실행)을 적고 같은 호출을 재시도한다

## File Structure

| 파일 | 책임 | Task |
|------|------|------|
| `src/infrastructure/browser/naver/selectors.py` (수정) | 로그인 페이지 셀렉터·판정 문구 | 1 |
| `src/infrastructure/browser/naver/login.py` (신규) | `LoginOutcome`, `classify_login_page`, `auto_login` | 1, 2 |
| `src/infrastructure/browser/naver/adapter.py` (수정) | `relogin()` | 2 |
| `src/infrastructure/config.py`, `.env.example` (수정) | 로그인·새 봇 설정값 | 3 |
| `src/application/use_cases/publish_selected_post.py`, `revise_selected_post.py` (수정) | `LOGGED_IN` 결과, `LOGIN_FAILED` 문구 상수 | 3 |
| `src/interface/web/platform.py` (수정) | 새 봇 알림 조립, 만료 알림 문구, 재로그인 작업 | 4 |
| `src/interface/web/app.py`, `templates/*.html` (수정) | 버튼·라우트·07:30 자동 실행 시각 | 5 |
| `src/interface/web/__main__.py` (수정) | 조립, 발행·수정 발행 로그인 실패 알림 | 5 |
| `scripts/naver_blog.py` (수정), `scripts/com.blog-automation.naver-session-check.plist` (신규) | `check --notify`, 07:30 실행 | 6 |
| `CLAUDE.md`, spec (수정) | 운영 문서 | 7 |

---

### Task 1: 로그인 화면 판정 (순수 함수)

**Files:**
- Modify: `src/infrastructure/browser/naver/selectors.py` (파일 끝에 추가)
- Create: `src/infrastructure/browser/naver/login.py`
- Test: `tests/unit/infrastructure/test_naver_login.py` (신규)

**Interfaces:**
- Produces: `LoginOutcome` (Enum: `SUCCESS`, `WAITING_APPROVAL`, `TIMEOUT`, `WRONG_PASSWORD`, `BLOCKED`, `UNKNOWN`), `LOGIN_MESSAGES: dict[LoginOutcome, str]`, `classify_login_page(url: str, page_text: str, has_captcha: bool) -> LoginOutcome`, `LOGIN_URL: str`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/infrastructure/test_naver_login.py`:

```python
"""네이버 자동 로그인 — 화면 판정과 입력 흐름 (브라우저 없음)."""
from __future__ import annotations

import pytest

from src.infrastructure.browser.naver.login import (
    LOGIN_MESSAGES,
    LoginOutcome,
    classify_login_page,
)

NID = "https://nid.naver.com/nidlogin.login"


@pytest.mark.parametrize(("url", "text", "captcha", "expected"), [
    ("https://www.naver.com/", "", False, LoginOutcome.SUCCESS),
    (NID, "아이디 또는 비밀번호를 잘못 입력했습니다.", False, LoginOutcome.WRONG_PASSWORD),
    (NID, "", True, LoginOutcome.BLOCKED),
    (NID, "자동입력 방지문자를 입력해 주세요", False, LoginOutcome.BLOCKED),
    (NID, "회원님의 아이디를 보호조치 하였습니다", False, LoginOutcome.BLOCKED),
    ("https://nid.naver.com/login/ext/deviceConfirm", "2단계 인증 알림을 보냈습니다",
     False, LoginOutcome.WAITING_APPROVAL),
    (NID, "처음 보는 화면", False, LoginOutcome.UNKNOWN),
])
def test_화면_판정(url, text, captcha, expected):
    assert classify_login_page(url, text, captcha) is expected


def test_캡차가_비밀번호_오류보다_먼저():
    # 캡차 화면에도 오류 문구가 함께 보일 수 있다 — 더 위험한 쪽(보호조치)으로 본다
    text = "비밀번호를 잘못 입력했습니다. 자동입력 방지문자를 입력해 주세요"
    assert classify_login_page(NID, text, False) is LoginOutcome.BLOCKED


def test_모든_결과에_안내_문구가_있다():
    assert set(LOGIN_MESSAGES) == set(LoginOutcome)
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/unit/infrastructure/test_naver_login.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.infrastructure.browser.naver.login'`

- [ ] **Step 3: 셀렉터·문구 추가**

`selectors.py` 끝에 추가:

```python
# --- 로그인 페이지 (nid.naver.com) — 자동 로그인(login.py) 전용 ---
LOGIN_ID_INPUT = "input#id"
LOGIN_PW_INPUT = "input#pw"
LOGIN_SUBMIT = "#log\\.login"
LOGIN_CAPTCHA = "#captcha"
# '로그인 상태 유지' — 없으면 경고만 하고 진행한다
LOGIN_KEEP = ["input#keep", "input[name='nvlong']"]
# 판정 문구. 네이버가 문구를 바꾸면 결과 불명으로 끝난다(성공으로 넘어가지 않음)
LOGIN_BLOCKED_MARKERS = ["자동입력 방지", "보호조치"]
LOGIN_WRONG_PASSWORD_MARKERS = ["비밀번호를 잘못"]
LOGIN_APPROVAL_MARKERS = ["2단계 인증", "인증 요청", "알림을 보냈"]
# 승인 뒤 '새로운 기기 등록' 화면 — 등록을 눌러야 다음 로그인에서 다시 묻지 않는다
LOGIN_DEVICE_MARKERS = ["새로운 기기", "자주 사용하는 기기"]
LOGIN_DEVICE_REGISTER = "//button[normalize-space()='등록'] | //a[normalize-space()='등록']"
```

- [ ] **Step 4: `login.py` 작성 (판정 부분)**

```python
"""네이버 자동 로그인 — 폰에서 세션을 되살리기 위한 대시보드 '네이버 다시 로그인' 전용.

버튼 1회에 제출 1회만 한다. 실패가 반복되면 네이버가 보호조치를 걸기 때문이다.
아이디·비밀번호는 입력란에 값으로만 넣고 로그·메시지·예외에 남기지 않는다.
"""
from __future__ import annotations

from enum import Enum

from src.infrastructure.browser.naver import selectors as sel

LOGIN_URL = "https://nid.naver.com/nidlogin.login"


class LoginOutcome(Enum):
    SUCCESS = "success"
    WAITING_APPROVAL = "waiting_approval"
    TIMEOUT = "timeout"
    WRONG_PASSWORD = "wrong_password"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


LOGIN_MESSAGES = {
    LoginOutcome.SUCCESS: "네이버 로그인 성공",
    LoginOutcome.WAITING_APPROVAL: "폰 네이버 앱에서 로그인을 승인하세요",
    LoginOutcome.TIMEOUT: "폰 승인 시간 초과 — 다시 눌러 주세요",
    LoginOutcome.WRONG_PASSWORD: "아이디·비밀번호 확인 필요 (.env의 NAVER_LOGIN_ID·NAVER_LOGIN_PW)",
    LoginOutcome.BLOCKED: "캡차·보호조치 — 맥에서 scripts/naver_blog.py login 으로 직접 로그인",
    LoginOutcome.UNKNOWN: "로그인 결과 불명 — 직접 확인",
}


def classify_login_page(url: str, page_text: str, has_captcha: bool) -> LoginOutcome:
    """제출 뒤 화면 판정. 로그인 페이지(nid)를 벗어났으면 성공으로 본다."""
    if "nid.naver.com" not in url:
        return LoginOutcome.SUCCESS
    if has_captcha or any(m in page_text for m in sel.LOGIN_BLOCKED_MARKERS):
        return LoginOutcome.BLOCKED
    if any(m in page_text for m in sel.LOGIN_WRONG_PASSWORD_MARKERS):
        return LoginOutcome.WRONG_PASSWORD
    if any(m in page_text for m in sel.LOGIN_APPROVAL_MARKERS):
        return LoginOutcome.WAITING_APPROVAL
    return LoginOutcome.UNKNOWN
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/unit/infrastructure/test_naver_login.py -v && ruff check src/infrastructure/browser/naver tests/unit/infrastructure/test_naver_login.py`
Expected: 9 PASS, ruff 0건

- [ ] **Step 6: 커밋**

```bash
W="/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation/.claude/worktrees/naver-pipeline"
git -C "$W" add src/infrastructure/browser/naver/selectors.py src/infrastructure/browser/naver/login.py tests/unit/infrastructure/test_naver_login.py
git -C "$W" commit -m "feat(infra): 네이버 로그인 화면 판정"   # + 트레일러 두 줄
```

---

### Task 2: 자동 입력 흐름과 `relogin()`

**Files:**
- Modify: `src/infrastructure/browser/naver/login.py`
- Modify: `src/infrastructure/browser/naver/adapter.py` (`login()` 아래에 메서드 추가, import 추가)
- Test: `tests/unit/infrastructure/test_naver_login.py`, `tests/unit/infrastructure/test_naver_adapter.py`

**Interfaces:**
- Consumes: Task 1 `LoginOutcome`, `LOGIN_MESSAGES`, `classify_login_page`, `LOGIN_URL`, 셀렉터
- Produces: `auto_login(sb, login_id: str, login_pw: str, timeout: float = 300, poll: float = 2.0, clock=time.monotonic, sleep=time.sleep) -> LoginOutcome`, `NaverBrowserAdapter.relogin(login_id: str, login_pw: str) -> tuple[bool, str]`

- [ ] **Step 1: 실패하는 테스트 작성 — `test_naver_login.py` 끝에 추가**

```python
import logging

from src.infrastructure.browser.naver import login as login_mod
from src.infrastructure.browser.naver import selectors as sel
from src.infrastructure.browser.naver.login import auto_login


class _FakeSb:
    """제출 뒤 화면을 states 순서대로 돌려주는 가짜 브라우저."""

    def __init__(self, states, missing=()):
        self.states = list(states)  # [(url, text, captcha), ...] — 폴링마다 하나씩, 마지막은 유지
        self.current = self.states[0]
        self.missing = set(missing)
        self.filled: dict[str, str] = {}
        self.clicks: list[str] = []
        self.opened: list[str] = []

    def open(self, url):
        self.opened.append(url)

    def execute_script(self, script, *args):
        if script is login_mod._SET_VALUE_JS:
            selector, value = args
            if selector in self.missing:
                return False
            self.filled[selector] = value
            return True
        if script is login_mod._CHECK_KEEP_JS:
            return True
        # 본문 읽기 = 폴링 한 번의 시작 → 다음 화면으로 넘어간다. url·captcha도 같은 화면에서 읽는다
        self.current = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return self.current[1]

    def get_current_url(self):
        return self.current[0]

    def is_element_present(self, selector):
        return selector == sel.LOGIN_CAPTCHA and self.current[2]

    def is_element_visible(self, selector):
        return selector == sel.LOGIN_DEVICE_REGISTER

    def click(self, selector):
        self.clicks.append(selector)


def _run(sb, timeout=300):
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds

    return auto_login(sb, "my-id", "secret-pw", timeout=timeout, poll=2.0,
                      clock=lambda: now[0], sleep=sleep)


def test_입력하고_한_번_제출한다():
    sb = _FakeSb([("https://www.naver.com/", "", False)])
    assert _run(sb) is LoginOutcome.SUCCESS
    assert sb.opened == [login_mod.LOGIN_URL]
    assert sb.filled == {sel.LOGIN_ID_INPUT: "my-id", sel.LOGIN_PW_INPUT: "secret-pw"}
    assert sb.clicks.count(sel.LOGIN_SUBMIT) == 1


def test_승인을_기다렸다가_성공():
    wait = ("https://nid.naver.com/login/ext/deviceConfirm", "2단계 인증 알림을 보냈습니다", False)
    sb = _FakeSb([wait, wait, ("https://www.naver.com/", "", False)])
    assert _run(sb) is LoginOutcome.SUCCESS
    assert sb.clicks.count(sel.LOGIN_SUBMIT) == 1


def test_비밀번호_오류와_캡차는_즉시_중단():
    for text, captcha, expected in [
        ("비밀번호를 잘못 입력했습니다", False, LoginOutcome.WRONG_PASSWORD),
        ("", True, LoginOutcome.BLOCKED),
    ]:
        sb = _FakeSb([("https://nid.naver.com/nidlogin.login", text, captcha)])
        assert _run(sb) is expected
        assert sb.clicks.count(sel.LOGIN_SUBMIT) == 1


def test_승인_대기가_끝나지_않으면_시간_초과():
    wait = ("https://nid.naver.com/login/ext/deviceConfirm", "2단계 인증 알림을 보냈습니다", False)
    assert _run(_FakeSb([wait]), timeout=10) is LoginOutcome.TIMEOUT


def test_모르는_화면이_끝나지_않으면_결과_불명():
    unknown = ("https://nid.naver.com/nidlogin.login", "처음 보는 화면", False)
    assert _run(_FakeSb([unknown]), timeout=10) is LoginOutcome.UNKNOWN


def test_새_기기_등록_화면이면_등록을_누른다():
    device = ("https://nid.naver.com/login/ext/device", "새로운 기기에서 로그인했습니다", False)
    sb = _FakeSb([device, ("https://www.naver.com/", "", False)])
    assert _run(sb) is LoginOutcome.SUCCESS
    assert sel.LOGIN_DEVICE_REGISTER in sb.clicks


def test_입력란이_없으면_제출하지_않는다():
    sb = _FakeSb([("https://nid.naver.com/nidlogin.login", "", False)],
                 missing={sel.LOGIN_PW_INPUT})
    assert _run(sb) is LoginOutcome.UNKNOWN
    assert sel.LOGIN_SUBMIT not in sb.clicks


def test_비밀번호와_아이디가_로그에_남지_않는다(caplog):
    caplog.set_level(logging.DEBUG)
    _run(_FakeSb([("https://nid.naver.com/nidlogin.login", "비밀번호를 잘못", False)]))
    _run(_FakeSb([("https://www.naver.com/", "", False)]))
    assert "secret-pw" not in caplog.text
    assert "my-id" not in caplog.text
```

`tests/unit/infrastructure/test_naver_adapter.py` 끝에 추가:

```python
from src.infrastructure.browser.naver import login as login_mod
from src.infrastructure.browser.naver.login import LoginOutcome


def _relogin_adapter(monkeypatch, outcome, session_ok=True):
    adapter = NaverBrowserAdapter("myblog")
    monkeypatch.setattr(adapter, "start", lambda: setattr(adapter, "_sb", object()))
    monkeypatch.setattr(adapter, "stop", lambda: setattr(adapter, "_sb", None))
    monkeypatch.setattr(login_mod, "auto_login", lambda sb, i, p: outcome)
    monkeypatch.setattr(editor, "is_logged_in", lambda sb, blog: session_ok)
    return adapter


def test_relogin_성공(monkeypatch):
    adapter = _relogin_adapter(monkeypatch, LoginOutcome.SUCCESS)
    assert adapter.relogin("id", "pw") == (True, "네이버 로그인 성공")
    assert adapter._sb is None  # 브라우저를 닫았다


def test_relogin_실패는_안내_문구(monkeypatch):
    adapter = _relogin_adapter(monkeypatch, LoginOutcome.WRONG_PASSWORD)
    ok, message = adapter.relogin("id", "pw")
    assert not ok and "NAVER_LOGIN_PW" in message


def test_relogin_로그인은_됐지만_블로그_세션_확인_실패(monkeypatch):
    adapter = _relogin_adapter(monkeypatch, LoginOutcome.SUCCESS, session_ok=False)
    ok, message = adapter.relogin("id", "pw")
    assert not ok and "직접 확인" in message


def test_relogin_값이_없으면_브라우저를_열지_않는다(monkeypatch):
    adapter = _relogin_adapter(monkeypatch, LoginOutcome.SUCCESS)
    started = []
    monkeypatch.setattr(adapter, "start", lambda: started.append(True))
    ok, message = adapter.relogin("", "")
    assert not ok and "NAVER_LOGIN_ID" in message and started == []
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/unit/infrastructure/test_naver_login.py tests/unit/infrastructure/test_naver_adapter.py -v`
Expected: FAIL — `ImportError: cannot import name 'auto_login'`, `AttributeError: ... no attribute 'relogin'`

- [ ] **Step 3: `login.py`에 입력 흐름 추가**

상단 import를 다음으로 바꾼다:

```python
from __future__ import annotations

import logging
import time
from enum import Enum

from src.infrastructure.browser.naver import selectors as sel

logger = logging.getLogger(__name__)
```

`classify_login_page` 아래에 추가:

```python
APPROVAL_TIMEOUT = 300

# 값은 인자로만 넘긴다 — 스크립트 문자열에 넣으면 드라이버 로그에 남을 수 있다
_SET_VALUE_JS = """
const [selector, value] = arguments;
const el = document.querySelector(selector);
if (!el) return false;
el.focus();
el.value = value;
el.dispatchEvent(new Event('input', {bubbles: true}));
el.dispatchEvent(new Event('change', {bubbles: true}));
return true;
"""
_CHECK_KEEP_JS = """
for (const selector of arguments[0]) {
  const el = document.querySelector(selector);
  if (el) { if (!el.checked) el.click(); return true; }
}
return false;
"""
_BODY_TEXT_JS = "return document.body ? document.body.innerText : '';"


def auto_login(sb, login_id: str, login_pw: str, timeout: float = APPROVAL_TIMEOUT,
               poll: float = 2.0, clock=time.monotonic, sleep=time.sleep) -> LoginOutcome:
    """로그인 페이지에 값을 넣고 한 번 제출한 뒤, 폰 승인을 기다리며 결과를 판정한다."""
    sb.open(LOGIN_URL)
    sleep(2)
    for selector, value in ((sel.LOGIN_ID_INPUT, login_id), (sel.LOGIN_PW_INPUT, login_pw)):
        if not sb.execute_script(_SET_VALUE_JS, selector, value):
            logger.error(f"로그인 입력란을 찾지 못함 — selectors 확인: {selector}")
            return LoginOutcome.UNKNOWN
    if not sb.execute_script(_CHECK_KEEP_JS, sel.LOGIN_KEEP):
        logger.warning("'로그인 상태 유지' 체크박스를 찾지 못함 — 세션이 짧게 끝날 수 있음")
    sb.click(sel.LOGIN_SUBMIT)
    logger.info("네이버 로그인 제출 — 폰 승인 대기")

    deadline = clock() + timeout
    last = LoginOutcome.UNKNOWN
    while True:
        sleep(poll)
        text = str(sb.execute_script(_BODY_TEXT_JS) or "")
        outcome = classify_login_page(
            str(sb.get_current_url()), text, bool(sb.is_element_present(sel.LOGIN_CAPTCHA)),
        )
        if outcome in (LoginOutcome.SUCCESS, LoginOutcome.WRONG_PASSWORD, LoginOutcome.BLOCKED):
            logger.info(f"네이버 로그인 결과: {outcome.value}")
            return outcome
        if any(m in text for m in sel.LOGIN_DEVICE_MARKERS) and sb.is_element_visible(
            sel.LOGIN_DEVICE_REGISTER
        ):
            sb.click(sel.LOGIN_DEVICE_REGISTER)
        # 모르는 화면도 바로 멈추지 않는다 — 네이버 2단계 화면 문구를 다 알 수 없어서,
        # 바로 멈추면 정상 승인 대기를 끊는다. 시간이 다 되면 결과 불명으로 끝낸다
        last = outcome
        if clock() >= deadline:
            final = LoginOutcome.TIMEOUT if last is LoginOutcome.WAITING_APPROVAL else last
            logger.warning(f"네이버 로그인 결과: {final.value}")
            return final
```

- [ ] **Step 4: `adapter.py`에 `relogin` 추가**

import에 `from src.infrastructure.browser.naver import login` 추가(기존 `editor` import 옆). `login()` 메서드 아래에 추가:

```python
    def relogin(self, login_id: str, login_pw: str) -> tuple[bool, str]:
        """대시보드 '네이버 다시 로그인' — 브라우저를 열어 자동 입력하고 폰 승인을 기다린다."""
        if not login_id or not login_pw:
            return False, "NAVER_LOGIN_ID·NAVER_LOGIN_PW가 .env에 없음"
        self.start()
        try:
            outcome = login.auto_login(self._sb, login_id, login_pw)
            if outcome is not login.LoginOutcome.SUCCESS:
                # 로그인 화면에는 아이디가 보이므로 실패 스크린샷을 남기지 않는다
                return False, login.LOGIN_MESSAGES[outcome]
            if not editor.is_logged_in(self._sb, self._blog_id):
                return False, "로그인은 됐지만 블로그 세션 확인 실패 — 직접 확인"
            return True, login.LOGIN_MESSAGES[login.LoginOutcome.SUCCESS]
        finally:
            self.stop()
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/unit/infrastructure/test_naver_login.py tests/unit/infrastructure/test_naver_adapter.py -v && ruff check src/ tests/ && mypy src/infrastructure/browser/naver --ignore-missing-imports`
Expected: 모두 PASS, ruff 0건, naver 모듈 mypy 새 오류 0건

- [ ] **Step 6: 커밋**

```bash
git -C "$W" add src/infrastructure/browser/naver/login.py src/infrastructure/browser/naver/adapter.py tests/unit/infrastructure/test_naver_login.py tests/unit/infrastructure/test_naver_adapter.py
git -C "$W" commit -m "feat(infra): 네이버 자동 로그인 입력 흐름과 relogin"   # + 트레일러
```

---

### Task 3: 설정값과 결과 종류

**Files:**
- Modify: `src/infrastructure/config.py`, `.env.example`
- Modify: `src/application/use_cases/publish_selected_post.py` (`ManualPublishOutcome`, 로그인 실패 문구)
- Modify: `src/application/use_cases/revise_selected_post.py:42`
- Test: `tests/unit/infrastructure/test_config_naver.py`, `tests/unit/application/test_publish_selected_post.py`

**Interfaces:**
- Produces: `Config.naver_login_id`, `Config.naver_login_pw`, `Config.naver_telegram_bot_token`, `Config.telegram_chat_id` (모두 `str`, 기본 `""`); `ManualPublishOutcome.LOGGED_IN = "logged_in"`; `LOGIN_FAILED = "로그인 실패"` (publish_selected_post.py 모듈 상수)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/infrastructure/test_config_naver.py` 끝에 추가:

```python
def test_네이버_로그인_설정(monkeypatch):
    monkeypatch.setenv("NAVER_LOGIN_ID", "id")
    monkeypatch.setenv("NAVER_LOGIN_PW", "pw")
    monkeypatch.setenv("NAVER_TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    config = Config.from_env()
    assert (config.naver_login_id, config.naver_login_pw) == ("id", "pw")
    assert config.naver_telegram_bot_token == "123:abc"
    assert config.telegram_chat_id == "42"


def test_네이버_로그인_설정_기본값(monkeypatch):
    for key in ("NAVER_LOGIN_ID", "NAVER_LOGIN_PW", "NAVER_TELEGRAM_BOT_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    config = Config.from_env()
    assert config.naver_login_id == config.naver_login_pw == config.naver_telegram_bot_token == ""
```

`tests/unit/application/test_publish_selected_post.py`: 파일 상단 import에 `LOGIN_FAILED`를 `publish_selected_post`에서 함께 가져오고, 기존 로그인 실패 테스트(`MockBrowserAdapter(login_success=False)`를 쓰는 테스트, 139행 근처)의 `assert "Tistory" not in result.message` 아래에 한 줄 추가:

```python
        assert result.message.startswith(LOGIN_FAILED)  # 대시보드가 이 접두어로 새 봇 알림
```

(수정 발행 쪽에는 로그인 실패 단위 테스트가 없다 — 같은 상수를 쓰므로 발행 쪽 테스트로 접두어를 고정한다.)

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/unit/infrastructure/test_config_naver.py tests/unit/application/test_publish_selected_post.py -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'naver_login_id'`, `ImportError: cannot import name 'LOGIN_FAILED'`

- [ ] **Step 3: 구현**

`config.py` 필드 끝에:

```python
    naver_login_id: str = ""
    naver_login_pw: str = ""
    naver_telegram_bot_token: str = ""
    telegram_chat_id: str = ""
```

`from_env()` 인자 끝에:

```python
            naver_login_id=os.getenv("NAVER_LOGIN_ID", ""),
            naver_login_pw=os.getenv("NAVER_LOGIN_PW", ""),
            naver_telegram_bot_token=os.getenv("NAVER_TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
```

`.env.example`의 `NAVER_SHEET_TAB=` 줄 아래에:

```
# 네이버 세션 원격 복구: 대시보드 '네이버 다시 로그인'이 자동 입력한다(2단계 인증 폰 승인 필요)
NAVER_LOGIN_ID=
NAVER_LOGIN_PW=
# 네이버 알림 전용 텔레그램 봇 (채팅은 TELEGRAM_CHAT_ID 그대로)
NAVER_TELEGRAM_BOT_TOKEN=
```

`publish_selected_post.py`: `ManualPublishOutcome`에 `LOGGED_IN = "logged_in"  # 대시보드 '네이버 다시 로그인' 성공` 추가. 클래스 정의 위(모듈 상수 영역)에 `LOGIN_FAILED = "로그인 실패"` 추가하고, 125행 문구를 `f"{LOGIN_FAILED} — 발행대기 유지"`로 바꾼다.

`revise_selected_post.py`: `from src.application.use_cases.publish_selected_post import LOGIN_FAILED`를 추가(이미 같은 모듈에서 다른 이름을 import하고 있으면 거기에 합친다)하고 42행을 `ManualPublishResult.failed(row_index, f"{LOGIN_FAILED} — 수정대기 유지")`로 바꾼다.

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/unit -q && ruff check src/ tests/`
Expected: 전부 PASS, ruff 0건

- [ ] **Step 5: 커밋**

```bash
git -C "$W" add src/infrastructure/config.py .env.example src/application/use_cases/publish_selected_post.py src/application/use_cases/revise_selected_post.py tests/unit/infrastructure/test_config_naver.py tests/unit/application/test_publish_selected_post.py
git -C "$W" commit -m "feat(app): 네이버 재로그인 설정값과 로그인 실패 문구 상수"   # + 트레일러
```

---

### Task 4: 새 봇 알림과 재로그인 작업 조립 (`platform.py`)

**Files:**
- Modify: `src/interface/web/platform.py`
- Test: `tests/unit/interface/test_web_platform.py`

**Interfaces:**
- Consumes: Task 2 `NaverBrowserAdapter.relogin`, Task 3 설정값·`LOGGED_IN`·`LOGIN_FAILED`
- Produces:
  - `naver_notifier(config: Config) -> NotificationPort` — 토큰·채팅 둘 다 있으면 `TelegramNotificationAdapter`, 아니면 `NullNotificationAdapter`
  - `dashboard_url(env: Mapping[str, str]) -> str` — `DASHBOARD_EXTRA_HOSTS` 첫 값으로 `https://<host>/`, 없으면 `""`
  - `session_expired_message(url: str) -> str`
  - `notify_if_expired(logged_in: bool, notifier: NotificationPort, url: str) -> bool` — 보냈으면 True
  - `notify_login_failure(result: ManualPublishResult, notifier: NotificationPort, url: str) -> None`
  - `build_relogin(config: Config, project_root: Path, lock: PipelineLockPort) -> Callable[[int], ManualPublishResult]`

- [ ] **Step 1: 실패하는 테스트 작성 — `test_web_platform.py` 끝에 추가**

```python
from src.application.use_cases.publish_selected_post import (
    LOGIN_FAILED,
    ManualPublishOutcome,
    ManualPublishResult,
)
from src.infrastructure.browser.naver.adapter import NaverBrowserAdapter as _Adapter
from src.infrastructure.notification.null_adapter import NullNotificationAdapter
from src.infrastructure.notification.telegram_adapter import TelegramNotificationAdapter
from src.interface.web.platform import (
    build_relogin,
    dashboard_url,
    naver_notifier,
    notify_if_expired,
    notify_login_failure,
    session_expired_message,
)


class _Notifier:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, message, level="INFO"):
        self.sent.append((message, level))
        return True


class _Lock:
    def __init__(self, free=True):
        self.free, self.released = free, False

    def acquire(self):
        return self.free

    def release(self):
        self.released = True


def test_새_봇은_토큰과_채팅이_모두_있을_때만(monkeypatch):
    monkeypatch.setenv("NAVER_TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    assert isinstance(naver_notifier(Config.from_env()), TelegramNotificationAdapter)
    monkeypatch.delenv("NAVER_TELEGRAM_BOT_TOKEN")
    assert isinstance(naver_notifier(Config.from_env()), NullNotificationAdapter)


def test_대시보드_주소():
    assert dashboard_url({"DASHBOARD_EXTRA_HOSTS": "mac.tail.ts.net, other"}) == \
        "https://mac.tail.ts.net/"
    assert dashboard_url({}) == ""


def test_만료_알림_문구():
    assert "네이버 다시 로그인" in session_expired_message("")
    assert session_expired_message("https://mac.ts.net/").endswith("https://mac.ts.net/")


def test_세션이_살아_있으면_알리지_않는다():
    n = _Notifier()
    assert notify_if_expired(True, n, "u") is False and n.sent == []
    assert notify_if_expired(False, n, "https://m/") is True
    assert n.sent[0][1] == "WARNING" and "https://m/" in n.sent[0][0]


def test_로그인_실패_결과만_알린다():
    n = _Notifier()
    notify_login_failure(ManualPublishResult.failed(2, "본문 없음"), n, "")
    assert n.sent == []
    notify_login_failure(ManualPublishResult.failed(2, f"{LOGIN_FAILED} — 발행대기 유지"), n, "")
    assert len(n.sent) == 1


def test_재로그인_작업_성공(config, tmp_path, monkeypatch):
    monkeypatch.setattr(_Adapter, "relogin", lambda self, i, p: (True, "네이버 로그인 성공"))
    lock = _Lock()
    result = build_relogin(config, tmp_path, lock)(0)
    assert result.outcome is ManualPublishOutcome.LOGGED_IN
    assert lock.released


def test_재로그인_작업_실패는_실패_결과(config, tmp_path, monkeypatch):
    monkeypatch.setattr(_Adapter, "relogin", lambda self, i, p: (False, "폰 승인 시간 초과"))
    result = build_relogin(config, tmp_path, _Lock())(0)
    assert result.outcome is ManualPublishOutcome.FAILED
    assert "시간 초과" in result.message


def test_재로그인은_락이_잡혀_있으면_거부(config, tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(_Adapter, "relogin", lambda self, i, p: called.append(1) or (True, ""))
    result = build_relogin(config, tmp_path, _Lock(free=False))(0)
    assert result.outcome is ManualPublishOutcome.REJECTED and called == []
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/unit/interface/test_web_platform.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_relogin'`

- [ ] **Step 3: 구현 — `platform.py`**

import 추가(알파벳 순서는 ruff가 맞춘다):

```python
from collections.abc import Callable, Mapping

from src.application.use_cases.publish_selected_post import (
    LOGIN_FAILED,
    ManualPublishOutcome,
    ManualPublishResult,
)
from src.domain.ports.pipeline_lock_port import PipelineLockPort
from src.infrastructure.notification.null_adapter import NullNotificationAdapter
from src.infrastructure.notification.telegram_adapter import TelegramNotificationAdapter
```


파일 끝에 추가:

```python
def naver_notifier(config: Config) -> NotificationPort:
    """네이버 알림 전용 새 봇. 토큰·채팅이 없으면 조용히 버린다(알림은 부가 기능)."""
    if config.naver_telegram_bot_token and config.telegram_chat_id:
        return TelegramNotificationAdapter(
            bot_token=config.naver_telegram_bot_token, chat_id=config.telegram_chat_id,
        )
    return NullNotificationAdapter()


def dashboard_url(env: Mapping[str, str]) -> str:
    hosts = [h.strip() for h in env.get("DASHBOARD_EXTRA_HOSTS", "").split(",") if h.strip()]
    return f"https://{hosts[0]}/" if hosts else ""


def session_expired_message(url: str) -> str:
    message = "네이버 세션 만료 — 대시보드에서 [네이버 다시 로그인]을 누르고 폰 네이버 앱에서 승인하세요"
    return f"{message}\n{url}" if url else message


def notify_if_expired(logged_in: bool, notifier: NotificationPort, url: str) -> bool:
    if logged_in:
        return False
    notifier.send(session_expired_message(url), "WARNING")
    return True


def notify_login_failure(
    result: ManualPublishResult, notifier: NotificationPort, url: str,
) -> None:
    if result.outcome is ManualPublishOutcome.FAILED and result.message.startswith(LOGIN_FAILED):
        notifier.send(session_expired_message(url), "WARNING")


def build_relogin(
    config: Config, project_root: Path, lock: PipelineLockPort,
) -> Callable[[int], ManualPublishResult]:
    """대시보드 작업 종류 'login'. 발행과 같은 브라우저 프로필을 쓰므로 같은 락을 잡는다."""

    def relogin(row_index: int) -> ManualPublishResult:
        if not lock.acquire():
            return ManualPublishResult.rejected(
                row_index, "자동 파이프라인이 실행 중 — 끝난 뒤 다시 시도하세요",
            )
        try:
            adapter = NaverBrowserAdapter(
                config.naver_blog_id,
                profile_dir=str(project_root / DEFAULT_PROFILE_DIR),
                min_delay=0,
                max_delay=0,
            )
            ok, message = adapter.relogin(config.naver_login_id, config.naver_login_pw)
        finally:
            lock.release()
        outcome = ManualPublishOutcome.LOGGED_IN if ok else ManualPublishOutcome.FAILED
        return ManualPublishResult(outcome, row_index, message)

    return relogin
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/unit/interface/test_web_platform.py -v && ruff check src/ tests/`
Expected: 모두 PASS, ruff 0건

- [ ] **Step 5: 커밋**

```bash
git -C "$W" add src/interface/web/platform.py tests/unit/interface/test_web_platform.py
git -C "$W" commit -m "feat(cli): 네이버 새 봇 알림과 재로그인 작업 조립"   # + 트레일러
```

---

### Task 5: 대시보드 버튼·라우트·조립

**Files:**
- Modify: `src/interface/web/app.py` (`JOB_LABELS`, `AUTOMATION_TIMES`, `_register_check_routes`)
- Modify: `src/interface/web/templates/dashboard.html`, `templates/job.html`
- Modify: `src/interface/web/__main__.py`
- Test: `tests/unit/interface/test_web_app.py`

**Interfaces:**
- Consumes: Task 3 `ManualPublishOutcome.LOGGED_IN`, Task 4 `build_relogin`, `naver_notifier`, `dashboard_url`, `notify_login_failure`
- Produces: `POST /naver/login` (이름 `naver_login`), jinja 전역 `login_enabled`, `PublishJobRunner(..., login=...)`

- [ ] **Step 1: 실패하는 테스트 작성 — `test_web_app.py` 끝에 추가**

```python
class TestNaverLogin:
    def _client(self, calls, now=NOON):
        def login(row):
            calls.append(row)
            return ManualPublishResult(ManualPublishOutcome.LOGGED_IN, row, "네이버 로그인 성공")

        runner = PublishJobRunner(
            publish=lambda row: ManualPublishResult(ManualPublishOutcome.PUBLISHED, row, "ok"),
            login=login,
        )
        app = create_app(
            authenticator=AdminAuthenticator("admin", generate_password_hash(PASSWORD)),
            list_posts=ListPostsUseCase(InMemoryPostRepository([])),
            job_runner=runner,
            secret_key="test-secret-key-0123456789",
            clock=lambda: now,
        )
        app.config["TESTING"] = True
        client = app.test_client()
        html = client.get("/login").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        client.post("/login", data={"username": "admin", "password": PASSWORD, "csrf_token": token})
        return client, runner

    def _token(self, client):
        html = client.get("/").get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def test_네이버_대시보드에만_버튼이_있다(self):
        client, _ = self._client([])
        assert 'action="/naver/login"' in client.get("/").get_data(as_text=True)
        h = Harness()
        h.login()
        assert 'action="/naver/login"' not in h.client.get("/").get_data(as_text=True)
        assert h.client.post("/naver/login", data={"csrf_token": h.csrf("/")}).status_code == 404

    def test_로그인은_작업으로_돈다(self):
        calls: list[int] = []
        client, runner = self._client(calls)
        resp = client.post("/naver/login", data={"csrf_token": self._token(client)})
        job_id = resp.headers["Location"].rsplit("/", 1)[-1]
        job = runner.wait(job_id, timeout=5)
        assert job.result.outcome is ManualPublishOutcome.LOGGED_IN and calls == [0]
        html = client.get(f"/jobs/{job_id}").get_data(as_text=True)
        assert "notice-success" in html and "네이버 로그인" in html

    def test_CSRF_없으면_거부(self):
        calls: list[int] = []
        client, _ = self._client(calls)
        assert client.post("/naver/login").status_code == 400
        assert calls == []

    def test_자동_실행_직전에는_거부(self):
        calls: list[int] = []
        client, _ = self._client(calls, now=datetime(2026, 9, 28, 8, 50))
        resp = client.post("/naver/login", data={"csrf_token": self._token(client)},
                           follow_redirects=True)
        assert "09:00 자동 실행" in resp.get_data(as_text=True) and calls == []


def test_아침_점검_시각도_자동_실행으로_본다():
    found = automation_soon(datetime(2026, 9, 28, 7, 20))
    assert found is not None and found.strftime("%H:%M") == "07:30"
```

(`TestGenerate._client`와 같은 방식이다. CSRF 없는 POST가 이 앱에서 400이 아니라 다른 코드면 — 기존 CSRF 테스트의 기대값을 찾아 그 값으로 맞춘다.)

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/unit/interface/test_web_app.py -v -k "NaverLogin or 아침_점검"`
Expected: FAIL — `TypeError: PublishJobRunner.__init__() got an unexpected keyword argument 'login'`

- [ ] **Step 3: 구현 — `jobs.py`**

`PublishJobRunner.__init__` 인자 끝에 `login: Callable[[int], ManualPublishResult] | None = None,`를 추가하고 `tasks` dict에 `"login": login`을 넣는다.

- [ ] **Step 4: 구현 — `app.py`**

```python
AUTOMATION_TIMES = (time(0, 0), time(7, 30), time(8, 30), time(9, 0), time(10, 0), time(14, 0),
                    time(14, 30))  # 07:30 = 네이버 세션 아침 점검(같은 락을 잡는다)
```

```python
JOB_LABELS = {"publish": "수동 발행", "draft": "임시저장 시험", "generate": "글 생성",
              "revise": "수정 발행", "login": "네이버 로그인"}
```

`_register_check_routes`의 jinja 전역 설정 줄들 아래에 `app.jinja_env.globals["login_enabled"] = runner.enabled("login")`을 추가하고, `/generate` 라우트 아래에 추가:

```python
    @app.post("/naver/login")
    def naver_login():  # type: ignore[no-untyped-def]
        if not runner.enabled("login"):
            abort(404)
        if _refuse_near_automation(clock):
            return redirect(url_for("index"))
        job_id = runner.submit(0, kind="login")
        if job_id is None:
            flash("이미 진행 중인 작업이 있습니다. 끝난 뒤 다시 시도하세요.", "error")
            return redirect(url_for("index"))
        return redirect(url_for("job_status", job_id=job_id))
```

- [ ] **Step 5: 구현 — 템플릿**

`dashboard.html`: 5행 진행 중 안내의 `{% if active_job.kind != "generate" %}`를 `{% if active_job.kind not in ("generate", "login") %}`로 바꾸고, `{% if active_job %} … {% elif generate_enabled %} … {% endif %}` 블록을 닫는 `{% endif %}`(14행 근처) **바로 다음 줄**에 다음 블록을 추가:

```html
{% if login_enabled and not active_job %}
<form method="post" action="{{ url_for('naver_login') }}" class="generate">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <button type="submit">네이버 다시 로그인</button>
  <span class="sub">세션이 만료됐을 때만. 누른 뒤 폰 네이버 앱에서 승인하세요(최대 5분).</span>
</form>
{% endif %}
```

`job.html`: `{% if job.kind == "generate" %}`를 `{% if job.kind in ("generate", "login") %}`로, `{% if job.kind != "generate" %}`를 `{% if job.kind not in ("generate", "login") %}`로 바꾸고, 21행 성공 판정 목록에 `'logged_in'`을 추가한다. 실행 중 안내를 위해 `<section class="card">` 바로 아래에 추가:

```html
{% if running and job.kind == "login" %}<p class="notice notice-info">폰 네이버 앱에서 로그인을 승인하세요.</p>{% endif %}
```

- [ ] **Step 6: 구현 — `__main__.py` 조립**

import에 `build_relogin, dashboard_url, naver_notifier, notify_login_failure`를 platform에서 추가. `_build_publisher`와 `_build_reviser`의 내부 함수에서 `result = use_case.execute(row_index)` 바로 뒤에 추가:

```python
        if profile.name == "naver":
            notify_login_failure(result, naver_notifier(config), dashboard_url(os.environ))
```

`PublishJobRunner(...)` 인자에 추가:

```python
            login=(
                build_relogin(config, PROJECT_ROOT, DirectoryPipelineLock(LOCK_DIR))
                if profile.name == "naver" else None
            ),
```

- [ ] **Step 7: 통과 확인**

Run: `python -m pytest tests/unit -q && ruff check src/ tests/ && mypy src/ --ignore-missing-imports 2>&1 | tail -1 && python -m src.interface.web --help`
Expected: 단위 테스트 전부 PASS, ruff 0건, mypy 오류 수가 작업 전보다 늘지 않음(작업 전 수를 먼저 기록), `--help` 정상

- [ ] **Step 8: 커밋**

```bash
git -C "$W" add src/interface/web/ tests/unit/interface/test_web_app.py
git -C "$W" commit -m "feat(cli): 대시보드 '네이버 다시 로그인' 버튼과 로그인 실패 알림"   # + 트레일러
```

---

### Task 6: 아침 점검 `check --notify`와 launchd plist

**Files:**
- Modify: `scripts/naver_blog.py`
- Create: `scripts/com.blog-automation.naver-session-check.plist`

**Interfaces:**
- Consumes: Task 4 `naver_notifier`, `dashboard_url`, `notify_if_expired`; 기존 `DirectoryPipelineLock`
- Produces: `python scripts/naver_blog.py check --notify` — 만료면 새 봇 알림(종료코드 1), 유효면 0, 락이 잡혀 있으면 건너뜀(0)

판정·알림 로직은 Task 4 함수(테스트 완료)를 부르기만 한다. 이 Task는 연결이라 단위 테스트 대신 Step 3의 실행 확인으로 검증한다.

- [ ] **Step 1: `naver_blog.py` 수정**

import에 추가:

```python
from src.infrastructure.config import Config  # noqa: E402
from src.infrastructure.locking.directory_lock import DirectoryPipelineLock  # noqa: E402
from src.interface.web.platform import (  # noqa: E402
    dashboard_url,
    naver_notifier,
    notify_if_expired,
)
```

`LOGIN_URL` 아래에 `LOCK_DIR = Path(__file__).resolve().parent.parent / ".pipeline_b.lock"  # 발행과 같은 락`.

`_check`를 다음으로 바꾼다:

```python
def _check(adapter: NaverBrowserAdapter, notify: bool) -> int:
    ok = adapter.login()
    print("세션 유효" if ok else "세션 만료 — login 을 다시 실행하세요.")
    if notify and notify_if_expired(ok, naver_notifier(Config.from_env()),
                                    dashboard_url(os.environ)):
        print("만료 알림 보냄")
    return 0 if ok else 1
```

`main()`에서 `sub.add_parser("check")`를 다음으로 바꾼다:

```python
    check = sub.add_parser("check")
    check.add_argument("--notify", action="store_true", help="만료면 네이버 봇으로 알림(07:30 launchd)")
```

`adapter.start()` 직전에 추가:

```python
    lock = None
    if args.cmd == "check" and args.notify:
        lock = DirectoryPipelineLock(LOCK_DIR)
        if not lock.acquire():
            print("다른 작업이 브라우저를 쓰는 중 — 오늘 점검은 건너뜀")
            return 0
```

`return _check(adapter)`를 `return _check(adapter, getattr(args, "notify", False))`로 바꾸고, 기존 `finally:` 블록 안 `adapter.stop()` 뒤에 추가:

```python
        if lock is not None:
            lock.release()
```

- [ ] **Step 2: plist 작성**

`scripts/com.blog-automation.naver-session-check.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<!-- 네이버 세션 아침 점검(만료일 때만 새 봇 알림). 설치:
     cp scripts/com.blog-automation.naver-session-check.plist ~/Library/LaunchAgents/
     launchctl load ~/Library/LaunchAgents/com.blog-automation.naver-session-check.plist -->
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>com.blog-automation.naver-session-check</string>
	<key>ProgramArguments</key>
	<array>
		<string>/Users/kimsanghyeon/.pyenv/versions/3.11.11/bin/python3</string>
		<string>/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation/scripts/naver_blog.py</string>
		<string>check</string>
		<string>--notify</string>
	</array>
	<key>WorkingDirectory</key>
	<string>/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation</string>
	<key>StartCalendarInterval</key>
	<dict>
		<key>Hour</key>
		<integer>7</integer>
		<key>Minute</key>
		<integer>30</integer>
	</dict>
	<key>StandardErrorPath</key>
	<string>/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation/logs/naver_session_check.err</string>
	<key>StandardOutPath</key>
	<string>/Users/kimsanghyeon/GitHub/Core Web Vitals/blog-automation/logs/naver_session_check.log</string>
</dict>
</plist>
```

- [ ] **Step 3: 확인**

Run: `python scripts/naver_blog.py check --help && plutil -lint scripts/com.blog-automation.naver-session-check.plist && ruff check scripts/naver_blog.py && python -m pytest tests/unit -q`
Expected: `--notify` 도움말 표시, plist `OK`, ruff 0건, 단위 테스트 전부 PASS.
실제 브라우저 점검은 실행하지 않는다(Task 8 실측에서 한다).

- [ ] **Step 4: 커밋**

```bash
git -C "$W" add scripts/naver_blog.py scripts/com.blog-automation.naver-session-check.plist
git -C "$W" commit -m "feat(scripts): 네이버 세션 아침 점검 check --notify와 launchd plist"   # + 트레일러
```

---

### Task 7: 문서

**Files:**
- Modify: `CLAUDE.md` (`### 네이버 블로그` 절)
- Modify: `docs/superpowers/specs/2026-09-30-naver-relogin-design.md`

- [ ] **Step 1: CLAUDE.md** — `### 네이버 블로그` 절의 `- 로그인은 사람이 한다: ...` 줄을 다음으로 바꾼다:

```markdown
- 로그인: 처음은 사람이 `python scripts/naver_blog.py login`('로그인 상태 유지' 체크), 세션은 `.browser_data_naver/`. 만료되면 대시보드 '네이버 다시 로그인'이 `.env`의 `NAVER_LOGIN_ID/PW`를 자동 입력하고 폰 네이버 앱 2단계 승인을 최대 300초 기다린다(`naver/login.py`). 버튼 1회에 제출 1회 — 비밀번호 오류·캡차는 즉시 중단(반복 실패는 보호조치). 07:30 launchd `com.blog-automation.naver-session-check`가 `check --notify`로 점검해 만료일 때만 새 봇(`NAVER_TELEGRAM_BOT_TOKEN`, 채팅 `TELEGRAM_CHAT_ID`)으로 알리고, 대시보드 발행·수정 발행이 로그인 실패로 끝나도 알린다. 07:30은 `AUTOMATION_TIMES`에도 들어 있다. `NAVER_BLOG_ID`는 로그인 아이디가 아니라 블로그 주소(`sangpedia`)
```

- [ ] **Step 2: spec 4장 표의 '알 수 없는 화면' 행을 구현에 맞춘다**

`| 알 수 없는 화면 | 위 어디에도 해당 없음 | 중단, "로그인 결과 불명 — 직접 확인". 성공으로 간주하지 않는다 |`를 다음으로 바꾼다:

`| 알 수 없는 화면 | 위 어디에도 해당 없음 | 바로 멈추지 않고 300초까지 지켜본다(2단계 화면 문구를 다 알 수 없어 정상 승인 대기를 끊지 않으려고). 끝까지 모르면 "로그인 결과 불명 — 직접 확인". 성공으로 간주하지 않는다 |`

그리고 표 아래에 한 줄 추가: `승인 뒤 '새로운 기기 등록' 화면이 나오면 '등록'을 누른다(문구·버튼은 selectors.py, 실측으로 확인).`

- [ ] **Step 3: 커밋**

```bash
git -C "$W" add CLAUDE.md docs/superpowers/specs/2026-09-30-naver-relogin-design.md
git -C "$W" commit -m "docs: 네이버 세션 원격 복구 운영 규칙"   # + 트레일러
```

---

### Task 8: 실측 (사용자 + Claude)

자동화할 수 없는 단계다. SDD 루프 밖에서 컨트롤러가 사용자와 진행한다.

- [ ] **Step 1 (사용자):** `.env`에 `NAVER_TELEGRAM_BOT_TOKEN`(재발급 권장)·`NAVER_LOGIN_ID`·`NAVER_LOGIN_PW` 추가, `@shykimsh_bot`에 `/start`
- [ ] **Step 2 (Claude):** 브랜치를 master에 fast-forward 병합하고 네이버 대시보드 재시작 — `git -C "<원 저장소>" merge --ff-only feat/naver-pipeline`, `launchctl kickstart -k gui/$(id -u)/com.blog-automation.naver-dashboard`, `/login` 200 확인
- [ ] **Step 3 (Claude):** 새 봇 시험 알림 1건 — `python -c "from dotenv import load_dotenv; load_dotenv(); from src.infrastructure.config import Config; from src.interface.web.platform import naver_notifier; print(naver_notifier(Config.from_env()).send('네이버 알림 봇 시험', 'INFO'))"` → `True`, 폰 도착 확인
- [ ] **Step 4 (사용자):** 폰 대시보드 '네이버 다시 로그인' → 폰 네이버 앱 승인 → 작업 화면 "네이버 로그인 성공". 실패면 결과 문구와 `logs/dashboard-web.log`로 `selectors.py` 문구·셀렉터를 조정(세션 유효 상태에서도 로그인 창은 열리므로 시험 가능 — 이미 로그인돼 있으면 nid가 바로 벗어나 성공으로 끝날 수 있음. 그 경우 입력 흐름은 다음 실제 만료 때 확인)
- [ ] **Step 5 (Claude, 사용자 승인 후):** plist 설치 — `cp scripts/com.blog-automation.naver-session-check.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.blog-automation.naver-session-check.plist`, `python scripts/naver_blog.py check --notify` 1회 → "세션 유효", 알림 없음
- [ ] **Step 6 (Claude):** 메모리 `naver-pipeline-in-progress.md`의 '보류: 네이버 자동 로그인'을 결과로 갱신
