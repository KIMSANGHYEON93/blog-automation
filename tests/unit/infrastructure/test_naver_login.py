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
    sb = _FakeSb([("https://nid.naver.com/nidlogin.login", "", False), ("https://www.naver.com/", "", False)])
    assert _run(sb) is LoginOutcome.SUCCESS
    assert sb.opened == [login_mod.LOGIN_URL]
    assert sb.filled == {sel.LOGIN_ID_INPUT: "my-id", sel.LOGIN_PW_INPUT: "secret-pw"}
    assert sb.clicks.count(sel.LOGIN_SUBMIT) == 1


def test_이미_로그인돼_있으면_입력하지_않고_성공():
    sb = _FakeSb([("https://www.naver.com/", "", False)])
    assert _run(sb) is LoginOutcome.SUCCESS
    assert sb.filled == {} and sel.LOGIN_SUBMIT not in sb.clicks


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


def test_기기_등록_화면이_여러_폴링에_남으면_한_번만_누른다():
    device = ("https://nid.naver.com/login/ext/device", "새로운 기기에서 로그인했습니다", False)
    sb = _FakeSb([device, device, device, ("https://www.naver.com/", "", False)])
    assert _run(sb) is LoginOutcome.SUCCESS
    assert sb.clicks.count(sel.LOGIN_DEVICE_REGISTER) == 1


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
