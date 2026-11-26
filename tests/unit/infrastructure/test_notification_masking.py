"""알림 어댑터 실패 로그 — 봇 토큰·웹훅 주소가 예외 문자열에 섞여도 남기지 않는다 (가짜 값)."""
from __future__ import annotations

import urllib.error

import pytest

from src.infrastructure.notification import slack_adapter, telegram_adapter
from src.infrastructure.notification.slack_adapter import SlackNotificationAdapter
from src.infrastructure.notification.telegram_adapter import TelegramNotificationAdapter

FAKE_BOT_TOKEN = "123456789:AAFakeBotToken_abc-DEF0123456789xyz"
FAKE_WEBHOOK = "https://hooks.slack.com/services/T0FAKE/B0FAKE/fakeSecretPart123"


def _raise_with(url: str):
    def fake_urlopen(req, timeout):
        raise urllib.error.URLError(f"connection reset while requesting {url}")
    return fake_urlopen


def test_텔레그램_실패_로그에_봇_토큰이_남지_않는다(monkeypatch, caplog):
    url = f"https://api.telegram.org/bot{FAKE_BOT_TOKEN}/sendMessage"
    monkeypatch.setattr(telegram_adapter.urllib.request, "urlopen", _raise_with(url))

    with caplog.at_level("WARNING"):
        ok = TelegramNotificationAdapter(FAKE_BOT_TOKEN, "1").send("hi")

    assert ok is False
    assert "Telegram 알림 전송 실패" in caplog.text
    assert FAKE_BOT_TOKEN not in caplog.text


@pytest.mark.parametrize("secret_part", ["fakeSecretPart123"])
def test_슬랙_실패_로그에_웹훅_주소가_남지_않는다(monkeypatch, caplog, secret_part):
    monkeypatch.setattr(slack_adapter.urllib.request, "urlopen", _raise_with(FAKE_WEBHOOK))

    with caplog.at_level("WARNING"):
        ok = SlackNotificationAdapter(FAKE_WEBHOOK).send("hi")

    assert ok is False
    assert secret_part not in caplog.text
