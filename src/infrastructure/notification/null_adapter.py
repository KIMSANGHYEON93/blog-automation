"""NullNotificationAdapter — 알림 미설정 시 사용하는 No-op 구현."""
from __future__ import annotations

import logging

from src.domain.ports.notification_port import NotificationPort

logger = logging.getLogger(__name__)


class NullNotificationAdapter(NotificationPort):
    """알림 미설정 시 사용. 메시지를 로그에만 기록."""

    def send(self, message: str, level: str = "INFO") -> bool:
        logger.debug(f"[NullNotification] ({level}) {message}")
        return True
