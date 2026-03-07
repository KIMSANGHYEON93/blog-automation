"""SlackNotificationAdapter — Slack Webhook 알림."""
from __future__ import annotations

import json
import logging
import urllib.request

from src.domain.ports.notification_port import NotificationPort

logger = logging.getLogger(__name__)

_LEVEL_EMOJI = {"INFO": ":white_check_mark:", "WARNING": ":warning:", "ERROR": ":x:"}


class SlackNotificationAdapter(NotificationPort):
    """Slack Incoming Webhook으로 알림 전송."""

    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url

    def send(self, message: str, level: str = "INFO") -> bool:
        emoji = _LEVEL_EMOJI.get(level, ":speech_balloon:")
        payload = json.dumps({
            "text": f"{emoji} [{level}] {message}",
        }).encode("utf-8")

        req = urllib.request.Request(
            self._webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return bool(resp.status == 200)
        except Exception as e:
            logger.warning(f"Slack 알림 전송 실패: {e}")
            return False
