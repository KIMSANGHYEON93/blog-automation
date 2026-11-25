"""로그인 제출 뒤 카카오 보안문제(캡차) 화면을 일반 로그인 실패와 구분한다.

2026-11-24·25 실측 화면: accounts.kakao.com/login/, 제목 '카카오계정',
표시 '안전한 서비스 이용을 위해 아래 문제에 답해 주세요.'
우회하지 않는다 — 감지해서 예외로 올릴 뿐이다.
"""
from __future__ import annotations

import pytest

from src.domain.exceptions import LoginChallengeError, LoginFailedError
from src.infrastructure.browser import kakao_auth

CHALLENGE_TEXT = (
    "안전한 서비스 이용을 위해 아래 문제에 답해 주세요. | Kakao | "
    "TIP 카카오메일이 있다면 메일 아이디만 입력해 보세요."
)
LOGIN_URL = "https://accounts.kakao.com/login/?continue=https%3A%2F%2Fkauth.kakao.com"


class AfterSubmitSB:
    """로그인 폼에 입력·제출하면 after_url/after_text 화면이 되는 브라우저."""

    def __init__(self, after_url=LOGIN_URL, after_text="", title="카카오계정"):
        self.url = LOGIN_URL
        self._after_url, self._after_text, self._title = after_url, after_text, title
        self.submitted = 0

    def wait_for_element_present(self, sel, timeout=1):
        if sel not in ("#loginId--1", "#password--2", "button.submit"):
            raise TimeoutError(sel)

    def click(self, sel):
        if sel == "button.submit":
            self.submitted += 1
            self.url = self._after_url

    def type(self, _sel, _value):
        pass

    def get_current_url(self):
        return self.url

    def get_title(self):
        return self._title

    def execute_script(self, script, *args):
        if "innerText" in script:
            return self._after_text
        return ""


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(kakao_auth.time, "sleep", lambda _s: None)


class TestDetect:
    def test_보안문제_화면이면_LoginChallengeError(self):
        sb = AfterSubmitSB(after_text=CHALLENGE_TEXT)
        with pytest.raises(LoginChallengeError):
            kakao_auth._enter_credentials_and_wait(sb, "id", "pw")

    def test_캡차는_로그인_실패의_한_종류다(self):
        """기존 경로(종료코드 1, 실패 처리)는 그대로 탄다."""
        assert issubclass(LoginChallengeError, LoginFailedError)

    def test_예외_메시지에_화면_문구가_남는다(self):
        sb = AfterSubmitSB(after_text=CHALLENGE_TEXT)
        with pytest.raises(LoginChallengeError, match="보안문제"):
            kakao_auth._enter_credentials_and_wait(sb, "id", "pw")

    @pytest.mark.parametrize("text", [
        "자동입력 방지 문자를 입력해 주세요",
        "보안문자를 입력해 주세요",
        "Please complete the CAPTCHA",
    ])
    def test_다른_캡차_문구도_감지한다(self, text):
        with pytest.raises(LoginChallengeError):
            kakao_auth._enter_credentials_and_wait(AfterSubmitSB(after_text=text), "id", "pw")

    def test_제출은_한_번뿐이다(self):
        """감지 뒤 다시 제출하면 반복 시도가 된다."""
        sb = AfterSubmitSB(after_text=CHALLENGE_TEXT)
        with pytest.raises(LoginChallengeError):
            kakao_auth._enter_credentials_and_wait(sb, "id", "pw")
        assert sb.submitted == 1


class TestNotChallenge:
    def test_비밀번호_오류는_캡차가_아니다(self):
        sb = AfterSubmitSB(after_text="비밀번호가 일치하지 않습니다")
        assert kakao_auth._enter_credentials_and_wait(sb, "id", "pw") is False

    def test_로그인_성공은_그대로_True(self):
        sb = AfterSubmitSB(after_url="https://www.tistory.com/")
        assert kakao_auth._enter_credentials_and_wait(sb, "id", "pw") is True

    def test_화면을_읽지_못해도_일반_실패로_끝난다(self):
        class Unreadable(AfterSubmitSB):
            def execute_script(self, script, *args):
                raise RuntimeError("no such window")

        assert kakao_auth._enter_credentials_and_wait(Unreadable(), "id", "pw") is False


class TestNotSwallowed:
    def test_kakao_login의_넓은_except가_삼키지_않는다(self):
        """kakao_login은 모든 예외를 False로 바꾼다 — 캡차까지 바꾸면 구분이 사라진다."""
        sb = AfterSubmitSB(after_text=CHALLENGE_TEXT)
        sb.open = lambda _url: None
        sb.is_element_visible = lambda sel: sel == "a.btn_login.link_kakao_id"
        original_click = sb.click

        def click(sel):
            if sel == "a.btn_login.link_kakao_id":
                sb.url = LOGIN_URL
            else:
                original_click(sel)

        sb.click = click
        with pytest.raises(LoginChallengeError):
            kakao_auth.kakao_login(sb, "id", "pw")
