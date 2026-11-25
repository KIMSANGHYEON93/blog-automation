"""캡차·당일 차단은 어댑터가 이미 한 번 알렸다 — main()의 크래시 알림을 겹쳐 보내지 않는다.

크래시 알림에는 '/retry_publish'가 붙는데, 캡차 상황에서 재실행을 권하면
반복 로그인 시도를 부추긴다. 종료코드는 그대로 0이 아니어야 한다(launchd 기록).
"""
from __future__ import annotations

import pytest

from src.domain.exceptions import LoginBlockedError, LoginChallengeError, LoginFailedError
from src.domain.ports.notification_port import NotificationPort
from src.interface import cli


class SpyNotifier(NotificationPort):
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, message: str, level: str = "INFO") -> bool:
        self.sent.append((level, message))
        return True


@pytest.fixture
def spy(monkeypatch):
    notifier = SpyNotifier()
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "setup_logging", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_build_notification", lambda: notifier)
    monkeypatch.setattr(cli.sys, "argv", ["cli"])
    return notifier


def fail_with(monkeypatch, error: Exception) -> None:
    def boom():
        raise error

    monkeypatch.setattr(cli, "_main_inner", boom)


@pytest.mark.parametrize("error", [
    LoginChallengeError("카카오 보안문제(캡차) 화면"),
    LoginBlockedError("오늘 캡차 감지 — 자동 로그인 건너뜀"),
])
def test_캡차와_당일_차단은_크래시_알림을_보내지_않는다(monkeypatch, spy, error):
    fail_with(monkeypatch, error)
    with pytest.raises(type(error)):
        cli.main()
    assert spy.sent == []


def test_일반_로그인_실패는_지금처럼_알린다(monkeypatch, spy):
    fail_with(monkeypatch, LoginFailedError("Tistory 로그인 실패 — 발행 중단"))
    with pytest.raises(LoginFailedError):
        cli.main()
    assert len(spy.sent) == 1
    assert "/retry_publish" in spy.sent[0][1]
