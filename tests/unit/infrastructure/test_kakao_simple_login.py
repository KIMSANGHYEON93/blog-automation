"""카카오 '간편로그인 계정 선택' 화면 — 2026-10-16부터 로그인 폼 대신 이 화면이 먼저 뜬다.

'로그인 상태 유지'를 켠 뒤(10-15) 카카오가 /login/simple/ 로 보내는데, 입력칸이 하나도
없어 폼 탐색이 전부 실패했다(10-16~19 발행 0건). 저장된 계정을 누르고, 안 넘어가면
'새로운 계정으로 로그인'으로 기존 폼 흐름에 합류한다.
"""
from __future__ import annotations

from src.infrastructure.browser import kakao_auth

SIMPLE_URL = (
    "https://accounts.kakao.com/login/simple/?continue="
    "https%3A%2F%2Fkauth.kakao.com%2Foauth%2Fauthorize%3Fclient_id%3Dx#simpleLogin"
)
FORM_URL = "https://accounts.kakao.com/login/?continue=https%3A%2F%2Fkauth.kakao.com%2Foauth"
KAUTH_URL = "https://kauth.kakao.com/oauth/authorize?client_id=x"


class FakeSB:
    """간편로그인 화면. 저장 계정 클릭이 먹히면 kauth로, 아니면 그대로 남는다."""

    def __init__(self, saved_works: bool):
        self.url = SIMPLE_URL
        self.saved_works = saved_works
        self.clicks: list[bool] = []

    def get_current_url(self):
        return self.url

    def execute_script(self, _script, saved):
        self.clicks.append(saved)
        if saved and self.saved_works:
            self.url = KAUTH_URL
        elif not saved:
            self.url = FORM_URL
        return True


class TestKauthUrl:
    def test_간편로그인_주소의_continue_파라미터는_kauth가_아니다(self):
        assert not kakao_auth._is_kauth(SIMPLE_URL)
        assert not kakao_auth._is_kauth(FORM_URL)

    def test_kauth_호스트만_kauth(self):
        assert kakao_auth._is_kauth(KAUTH_URL)


class TestLeaveSimpleLogin:
    def test_저장_계정이_먹히면_그것만_누른다(self, monkeypatch):
        monkeypatch.setattr(kakao_auth.time, "sleep", lambda _s: None)
        sb = FakeSB(saved_works=True)

        url = kakao_auth._leave_simple_login(sb)

        assert sb.clicks == [True]
        assert url == KAUTH_URL

    def test_저장_계정이_안_넘어가면_새_계정_로그인으로_폴백(self, monkeypatch):
        monkeypatch.setattr(kakao_auth.time, "sleep", lambda _s: None)
        sb = FakeSB(saved_works=False)

        url = kakao_auth._leave_simple_login(sb)

        assert sb.clicks == [True, False]
        assert url == FORM_URL

    def test_간편로그인_화면이_아니면_아무것도_안_누른다(self, monkeypatch):
        monkeypatch.setattr(kakao_auth.time, "sleep", lambda _s: None)
        sb = FakeSB(saved_works=True)
        sb.url = FORM_URL

        url = kakao_auth._leave_simple_login(sb)

        assert sb.clicks == []
        assert url == FORM_URL
