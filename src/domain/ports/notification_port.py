"""NotificationPort — Domain interface for notifications."""
from __future__ import annotations

from abc import ABC, abstractmethod


class NotificationPort(ABC):
    @abstractmethod
    def send(self, message: str, level: str = "INFO") -> bool:
        """알림 전송. level: INFO, WARNING, ERROR.

        Returns:
            True if sent successfully.
        """
        ...
