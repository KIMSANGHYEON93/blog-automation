"""텔레그램 재실행 봇 — 어떤 메시지를 명령으로 받아들이는지."""
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "telegram_retry_bot.py"
_spec = importlib.util.spec_from_file_location("telegram_retry_bot", _SCRIPT)
bot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bot)

CHAT = "12345"
NOW = 1_000_000


def _update(text, chat_id=12345, date=NOW):
    return {"update_id": 1, "message": {"chat": {"id": chat_id}, "date": date, "text": text}}


def test_발행_재실행은_인자_없이():
    assert bot.command_args(_update("/retry_publish"), CHAT, NOW) == []


def test_수정_재실행():
    assert bot.command_args(_update("/retry_revise"), CHAT, NOW) == ["--revise"]


def test_봇_멘션_형식도_받는다():
    assert bot.command_args(_update("/retry_revise@my_bot"), CHAT, NOW) == ["--revise"]


def test_다른_채팅은_무시():
    assert bot.command_args(_update("/retry_publish", chat_id=999), CHAT, NOW) is None


def test_모르는_명령은_무시():
    assert bot.command_args(_update("/retry_publish; rm -rf /"), CHAT, NOW) is None
    assert bot.command_args(_update("/retry_check_index"), CHAT, NOW) is None


def test_10분_지난_명령은_무시():
    assert bot.command_args(_update("/retry_publish", date=NOW - 601), CHAT, NOW) is None


def test_메시지_없는_업데이트는_무시():
    assert bot.command_args({"update_id": 1}, CHAT, NOW) is None
