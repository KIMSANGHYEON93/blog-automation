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
