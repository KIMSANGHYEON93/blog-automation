"""카카오 보안문제(캡차) 당일 차단 — 반복 로그인 시도가 계정 제한으로 번지지 않게.

2026-11-24·25: 09:00 발행이 캡차 화면에 막혔고, 같은 날 다른 모드가 또 로그인을
시도할 수 있었다. 캡차가 뜬 날은 사람이 로그인할 때까지 자동 로그인을 멈춘다.
"""
from __future__ import annotations

import json
from datetime import date

from src.infrastructure.browser.login_challenge_guard import LoginChallengeGuard

DAY1 = date(2026, 11, 25)
DAY2 = date(2026, 11, 26)


def guard_on(tmp_path, today=DAY1) -> LoginChallengeGuard:
    return LoginChallengeGuard(tmp_path / "block.json", today=lambda: today)


class TestBlock:
    def test_기록이_없으면_차단되지_않는다(self, tmp_path):
        assert guard_on(tmp_path).is_blocked() is False

    def test_차단한_날은_차단된다(self, tmp_path):
        guard = guard_on(tmp_path)
        guard.block("보안문제 화면")
        assert guard.is_blocked() is True

    def test_처음_차단할_때만_True를_돌려준다(self, tmp_path):
        """알림을 1회만 보내기 위한 신호 — 같은 날 두 번째 차단은 새 사건이 아니다."""
        guard = guard_on(tmp_path)
        assert guard.block("첫 감지") is True
        assert guard.block("또 감지") is False

    def test_다음_날이면_자동으로_풀린다(self, tmp_path):
        guard_on(tmp_path, DAY1).block("보안문제 화면")
        assert guard_on(tmp_path, DAY2).is_blocked() is False

    def test_다음_날_다시_감지하면_새_사건이다(self, tmp_path):
        guard_on(tmp_path, DAY1).block("어제")
        assert guard_on(tmp_path, DAY2).block("오늘") is True

    def test_기록에_날짜와_사유가_남는다(self, tmp_path):
        guard_on(tmp_path).block("보안문제 화면")
        saved = json.loads((tmp_path / "block.json").read_text(encoding="utf-8"))
        assert saved["blocked_on"] == "2026-11-25"
        assert saved["reason"] == "보안문제 화면"


class TestClear:
    def test_해제하면_같은_날이라도_풀린다(self, tmp_path):
        """사람이 로그인에 성공하면 그날 남은 자동 실행은 다시 돌아야 한다."""
        guard = guard_on(tmp_path)
        guard.block("보안문제 화면")
        guard.clear()
        assert guard.is_blocked() is False
        assert not (tmp_path / "block.json").exists()

    def test_기록이_없어도_해제는_조용히_끝난다(self, tmp_path):
        guard_on(tmp_path).clear()


class TestBrokenFile:
    def test_손상된_기록은_차단으로_보지_않는다(self, tmp_path):
        (tmp_path / "block.json").write_text("{not json", encoding="utf-8")
        assert guard_on(tmp_path).is_blocked() is False

    def test_디렉토리가_없으면_만들어_기록한다(self, tmp_path):
        guard = LoginChallengeGuard(tmp_path / "nested" / "block.json", today=lambda: DAY1)
        guard.block("보안문제 화면")
        assert guard.is_blocked() is True
