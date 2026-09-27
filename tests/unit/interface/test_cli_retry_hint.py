"""실패 알림에 붙는 텔레그램 재실행 명령."""
from src.interface.cli import retry_hint


def test_기본_발행_실패는_발행_재실행():
    assert "/retry_publish" in retry_hint([])


def test_수정_실패는_수정_재실행():
    assert "/retry_revise" in retry_hint(["--revise"])


def test_다른_모드는_힌트_없음():
    assert retry_hint(["--check-index"]) == ""
