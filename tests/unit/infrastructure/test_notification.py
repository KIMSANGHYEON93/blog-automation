"""NotificationPort 어댑터 테스트."""
from __future__ import annotations

from src.domain.ports.notification_port import NotificationPort
from src.infrastructure.notification.null_adapter import NullNotificationAdapter


class TestNullNotificationAdapter:
    def test_send_항상_True(self):
        """NullAdapter는 항상 True 반환."""
        adapter = NullNotificationAdapter()
        assert adapter.send("테스트 메시지") is True
        assert adapter.send("에러 발생", level="ERROR") is True

    def test_포트_구현_확인(self):
        """NullNotificationAdapter는 NotificationPort 구현."""
        adapter = NullNotificationAdapter()
        assert isinstance(adapter, NotificationPort)


class _RecordingAdapter(NotificationPort):
    """테스트용 알림 기록 어댑터."""

    def __init__(self):
        self.messages: list[tuple[str, str]] = []

    def send(self, message: str, level: str = "INFO") -> bool:
        self.messages.append((message, level))
        return True


class TestNotificationPort:
    def test_다중_알림_전송(self):
        """여러 레벨의 알림 전송 기록."""
        adapter = _RecordingAdapter()

        adapter.send("발행 완료: 5건", "INFO")
        adapter.send("발행 실패: 2건", "ERROR")
        adapter.send("CWV 경고: LCP > 2.5s", "WARNING")

        assert len(adapter.messages) == 3
        assert adapter.messages[0] == ("발행 완료: 5건", "INFO")
        assert adapter.messages[1] == ("발행 실패: 2건", "ERROR")
        assert adapter.messages[2] == ("CWV 경고: LCP > 2.5s", "WARNING")
