"""2FA 감지 시 즉시 알림 — 조용히 120초 기다리다 죽으면 승인할 기회가 없다.

카카오톡 푸시 승인은 사람이 눌러야 하므로 무인 통과는 불가능하다.
대신 감지 순간 알림을 보내면 '발행 중단'이 '몇 분 지연'으로 내려간다.
"""
from __future__ import annotations

from src.domain.ports.notification_port import NotificationPort
from src.infrastructure.browser import kakao_auth


class SpyNotifier(NotificationPort):
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, message: str, level: str = "INFO") -> bool:
        self.sent.append((level, message))
        return True


class FakeSB:
    """2FA 화면에 멈춰 있는 브라우저 — 승인이 영영 안 온다."""

    def __init__(self, url="https://accounts.kakao.com/two-step-verification"):
        self._url = url

    def get_current_url(self):
        return self._url

    def is_element_visible(self, _sel):
        return False

    def click(self, _sel):
        raise AssertionError("클릭 대상 없음")

    def execute_script(self, _script):
        return None


class TestTwoFaWindow:
    def test_대기_시간이_승인_가능하게_늘어났다(self):
        assert kakao_auth.TWO_FA_WAIT_SEC >= 300, (
            "120초는 알림을 보고 휴대폰을 열기에 짧다"
        )


class TestTwoFaAlert:
    def test_감지_즉시_알림이_나간다(self, monkeypatch):
        monkeypatch.setattr(kakao_auth.time, "sleep", lambda _s: None)
        monkeypatch.setattr(kakao_auth, "TWO_FA_WAIT_SEC", 6)
        spy = SpyNotifier()

        kakao_auth._handle_two_fa(FakeSB(), notifier=spy)

        assert spy.sent, "2FA 감지 알림이 없음 — 사용자가 승인할 기회를 못 얻는다"
        level, msg = spy.sent[0]
        assert level in ("WARNING", "ERROR")
        assert "2단계 인증" in msg or "2FA" in msg

    def test_알림은_대기_전에_한_번만(self, monkeypatch):
        monkeypatch.setattr(kakao_auth.time, "sleep", lambda _s: None)
        monkeypatch.setattr(kakao_auth, "TWO_FA_WAIT_SEC", 30)
        spy = SpyNotifier()

        kakao_auth._handle_two_fa(FakeSB(), notifier=spy)

        assert len(spy.sent) == 1, f"폴링마다 보내면 도배된다: {len(spy.sent)}건"

    def test_notifier_없이도_동작한다(self, monkeypatch):
        """알림 채널 미설정 환경에서 로그인이 깨지면 안 된다."""
        monkeypatch.setattr(kakao_auth.time, "sleep", lambda _s: None)
        monkeypatch.setattr(kakao_auth, "TWO_FA_WAIT_SEC", 6)

        assert kakao_auth._handle_two_fa(FakeSB()) is False

    def test_알림_전송_실패가_로그인을_깨지_않는다(self, monkeypatch):
        monkeypatch.setattr(kakao_auth.time, "sleep", lambda _s: None)
        monkeypatch.setattr(kakao_auth, "TWO_FA_WAIT_SEC", 6)

        class Broken(NotificationPort):
            def send(self, message: str, level: str = "INFO") -> bool:
                raise RuntimeError("웹훅 다운")

        assert kakao_auth._handle_two_fa(FakeSB(), notifier=Broken()) is False
