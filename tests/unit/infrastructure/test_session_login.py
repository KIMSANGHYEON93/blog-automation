"""저장된 세션으로 로그인을 건너뛴다 — 카카오 OAuth를 안 타면 2FA도 안 뜬다."""
from __future__ import annotations

from src.infrastructure.browser.session_login import try_session_login


class FakeSB:
    def __init__(self, manage_ok: bool):
        self._manage_ok = manage_ok
        self.added: list[dict] = []
        self.opened: list[str] = []

    def open(self, url):
        self.opened.append(url)

    def add_cookie(self, c):
        self.added.append(c)

    def get_current_url(self):
        return ("https://blog.tistory.com/manage/posts" if self._manage_ok
                else "https://www.tistory.com/auth/login?redirect=...")


def cookie(name="__T_"):
    return {"name": name, "value": "v", "domain": ".blog.tistory.com", "path": "/"}


class TestNoStoredSession:
    def test_쿠키가_없으면_False(self):
        sb = FakeSB(manage_ok=True)
        assert try_session_login(sb, "blog", []) is False
        assert sb.added == []


class TestRestore:
    def test_쿠키를_주입하고_관리페이지로_검증한다(self):
        sb = FakeSB(manage_ok=True)
        assert try_session_login(sb, "blog", [cookie(), cookie("__T_SECURE")]) is True
        assert len(sb.added) == 2
        assert any("/manage" in u for u in sb.opened)

    def test_로그인_페이지로_튕기면_False(self):
        """서버 세션이 죽었다 — 정규 로그인으로 넘어가야 한다."""
        sb = FakeSB(manage_ok=False)
        assert try_session_login(sb, "blog", [cookie()]) is False

    def test_쿠키_주입_실패는_False(self):
        class Broken(FakeSB):
            def add_cookie(self, c):
                raise RuntimeError("도메인 불일치")

        assert try_session_login(Broken(manage_ok=True), "blog", [cookie()]) is False

    def test_쿠키_주입_전에_도메인_페이지를_먼저_연다(self):
        """다른 도메인에 있으면 add_cookie가 거부된다."""
        sb = FakeSB(manage_ok=True)
        try_session_login(sb, "blog", [cookie()])
        assert sb.opened[0].startswith("https://blog.tistory.com")

    def test_예외가_나도_죽지_않는다(self):
        class Exploding(FakeSB):
            def get_current_url(self):
                raise RuntimeError("드라이버 사망")

        assert try_session_login(Exploding(manage_ok=True), "blog", [cookie()]) is False
