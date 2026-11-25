"""SeleniumBrowserAdapter.login() — 캡차 감지 시 알림 1회 + 당일 자동 로그인 차단.

모든 모드(발행·수정·복구·대시보드 수동 발행)가 이 login()을 지나므로
차단은 여기 한 곳에서 건다. 실제 브라우저·카카오 로그인은 쓰지 않는다.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.domain.exceptions import LoginBlockedError, LoginChallengeError, LoginFailedError
from src.domain.ports.notification_port import NotificationPort
from src.domain.value_objects.credentials import Credentials
from src.infrastructure.browser import selenium_adapter
from src.infrastructure.browser.selenium_adapter import SeleniumBrowserAdapter

DAY1 = date(2026, 11, 25)
DAY2 = date(2026, 11, 26)


class SpyNotifier(NotificationPort):
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, message: str, level: str = "INFO") -> bool:
        self.sent.append((level, message))
        return True


class FakeSB:
    def __init__(self, url="https://myblog.tistory.com/manage/posts"):
        self.url = url
        self.opened: list[str] = []

    def open(self, url):
        self.opened.append(url)

    def get_current_url(self):
        return self.url

    def get_cookies(self):
        return [{"name": "__T_", "value": "v", "domain": ".myblog.tistory.com", "path": "/"}]


class KakaoScript:
    """kakao_login 대역 — 호출 횟수를 세고 정해진 결과를 낸다."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    def __call__(self, sb, kakao_id, kakao_pw, notifier=None):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def make_adapter(tmp_path, notifier=None, today=DAY1) -> SeleniumBrowserAdapter:
    adapter = SeleniumBrowserAdapter(
        Credentials(kakao_id="id", kakao_pw="pw", tistory_blog="myblog"),
        user_data_dir=str(tmp_path),
        notifier=notifier,
        today=lambda: today,
    )
    adapter._sb = FakeSB()
    return adapter


@pytest.fixture
def no_session(monkeypatch):
    monkeypatch.setattr(selenium_adapter, "try_session_login", lambda *a, **k: False)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(selenium_adapter.time, "sleep", lambda _s: None)


def use_kakao(monkeypatch, outcome) -> KakaoScript:
    script = KakaoScript(outcome)
    monkeypatch.setattr(selenium_adapter, "kakao_login", script)
    return script


CHALLENGE = LoginChallengeError("카카오 보안문제(캡차) 화면")


class TestChallengeDetected:
    def test_캡차면_예외가_그대로_올라간다(self, tmp_path, monkeypatch, no_session):
        use_kakao(monkeypatch, CHALLENGE)
        with pytest.raises(LoginChallengeError):
            make_adapter(tmp_path).login()

    def test_텔레그램으로_한_번_알린다(self, tmp_path, monkeypatch, no_session):
        use_kakao(monkeypatch, CHALLENGE)
        spy = SpyNotifier()
        with pytest.raises(LoginChallengeError):
            make_adapter(tmp_path, spy).login()

        assert len(spy.sent) == 1
        level, msg = spy.sent[0]
        assert level == "ERROR"
        assert "myblog" in msg, "어느 블로그인지"
        assert "2026-11-25" in msg, "언제인지"
        assert "scripts/tistory_login.py" in msg, "사람이 할 일(수동 로그인 방법)"

    def test_알림_전송_실패가_차단을_막지_않는다(self, tmp_path, monkeypatch, no_session):
        class Broken(NotificationPort):
            def send(self, message: str, level: str = "INFO") -> bool:
                raise RuntimeError("텔레그램 다운")

        use_kakao(monkeypatch, CHALLENGE)
        with pytest.raises(LoginChallengeError):
            make_adapter(tmp_path, Broken()).login()

        kakao = use_kakao(monkeypatch, True)
        with pytest.raises(LoginBlockedError):
            make_adapter(tmp_path).login()
        assert kakao.calls == 0


class TestSameDayBlocked:
    def test_같은_날_다음_실행은_카카오_로그인을_시도하지_않는다(
        self, tmp_path, monkeypatch, no_session,
    ):
        use_kakao(monkeypatch, CHALLENGE)
        with pytest.raises(LoginChallengeError):
            make_adapter(tmp_path).login()

        kakao = use_kakao(monkeypatch, True)
        with pytest.raises(LoginBlockedError):
            make_adapter(tmp_path).login()
        assert kakao.calls == 0, "차단된 날 카카오 OAuth를 다시 타면 계정 제한 위험"

    def test_차단도_로그인_실패의_한_종류다(self):
        assert issubclass(LoginBlockedError, LoginFailedError)

    def test_차단된_실행은_알림을_다시_보내지_않는다(self, tmp_path, monkeypatch, no_session):
        use_kakao(monkeypatch, CHALLENGE)
        spy = SpyNotifier()
        with pytest.raises(LoginChallengeError):
            make_adapter(tmp_path, spy).login()
        for _ in range(3):  # 10:00 revise, 대시보드 수동 발행 등
            with pytest.raises(LoginBlockedError):
                make_adapter(tmp_path, spy).login()
        assert len(spy.sent) == 1

    def test_차단_메시지에_수동_로그인_방법이_있다(self, tmp_path, monkeypatch, no_session):
        """대시보드는 예외 메시지를 그대로 화면에 보여 준다."""
        use_kakao(monkeypatch, CHALLENGE)
        with pytest.raises(LoginChallengeError):
            make_adapter(tmp_path).login()
        with pytest.raises(LoginBlockedError, match="scripts/tistory_login.py"):
            make_adapter(tmp_path).login()


class TestRelease:
    def test_다음_날이면_다시_로그인한다(self, tmp_path, monkeypatch, no_session):
        use_kakao(monkeypatch, CHALLENGE)
        with pytest.raises(LoginChallengeError):
            make_adapter(tmp_path, today=DAY1).login()

        kakao = use_kakao(monkeypatch, True)
        assert make_adapter(tmp_path, today=DAY2).login() is True
        assert kakao.calls == 1

    def test_저장된_세션이_살아_있으면_통과하고_차단을_푼다(self, tmp_path, monkeypatch):
        """세션 복원은 카카오를 타지 않는다 — 사람이 로그인해 세션을 남겼다는 뜻이다."""
        monkeypatch.setattr(selenium_adapter, "try_session_login", lambda *a, **k: False)
        use_kakao(monkeypatch, CHALLENGE)
        with pytest.raises(LoginChallengeError):
            make_adapter(tmp_path).login()

        monkeypatch.setattr(selenium_adapter, "try_session_login", lambda *a, **k: True)
        assert make_adapter(tmp_path).login() is True

        monkeypatch.setattr(selenium_adapter, "try_session_login", lambda *a, **k: False)
        kakao = use_kakao(monkeypatch, True)
        assert make_adapter(tmp_path).login() is True
        assert kakao.calls == 1

    def test_일반_로그인_실패는_차단하지_않는다(self, tmp_path, monkeypatch, no_session):
        """비밀번호 오류·2FA 미승인은 캡차가 아니다 — 기존 동작(False) 유지."""
        use_kakao(monkeypatch, False)
        assert make_adapter(tmp_path).login() is False
        kakao = use_kakao(monkeypatch, True)
        assert make_adapter(tmp_path).login() is True
        assert kakao.calls == 1


class TestManualLogin:
    def test_사람이_로그인한_브라우저를_확인하고_세션을_저장한다(
        self, tmp_path, monkeypatch, no_session,
    ):
        use_kakao(monkeypatch, CHALLENGE)
        with pytest.raises(LoginChallengeError):
            make_adapter(tmp_path).login()

        adapter = make_adapter(tmp_path)
        assert adapter.adopt_manual_login() is True
        assert any("/manage" in u for u in adapter._sb.opened)
        assert (tmp_path / selenium_adapter.SESSION_FILENAME).exists()

        kakao = use_kakao(monkeypatch, True)
        assert make_adapter(tmp_path).login() is True, "수동 로그인 성공 뒤엔 차단이 풀린다"
        assert kakao.calls == 1

    def test_로그인이_안_됐으면_차단을_유지한다(self, tmp_path, monkeypatch, no_session):
        use_kakao(monkeypatch, CHALLENGE)
        with pytest.raises(LoginChallengeError):
            make_adapter(tmp_path).login()

        adapter = make_adapter(tmp_path)
        adapter._sb = FakeSB(url="https://www.tistory.com/auth/login?redirect=...")
        assert adapter.adopt_manual_login() is False
        with pytest.raises(LoginBlockedError):
            make_adapter(tmp_path).login()
