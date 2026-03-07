"""TelegramNotificationAdapter — Telegram Bot API 알림."""
from __future__ import annotations

import json
import logging
import urllib.request

from src.domain.ports.notification_port import NotificationPort

logger = logging.getLogger(__name__)

_LEVEL_ICON = {"INFO": "\u2705", "WARNING": "\u26a0\ufe0f", "ERROR": "\u274c"}


class TelegramNotificationAdapter(NotificationPort):
    """Telegram Bot API로 알림 전송."""

    def __init__(self, bot_token: str, chat_id: str):
        self._bot_token = bot_token
        self._chat_id = chat_id

    def send(self, message: str, level: str = "INFO") -> bool:
        icon = _LEVEL_ICON.get(level, "")
        text = f"{icon} [{level}] {message}"

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return bool(resp.status == 200)
        except Exception as e:
            logger.warning(f"Telegram 알림 전송 실패: {e}")
            return False
