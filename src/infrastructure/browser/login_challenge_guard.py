"""LoginChallengeGuard — 카카오 보안문제(캡차)가 뜬 날은 자동 로그인을 멈춘다.

2026-11-24·25: 09:00 발행이 캡차 화면에 막혔다. 같은 날 다른 모드(10:00 수정,
대시보드 수동 발행 등)가 또 카카오 로그인을 시도하면 반복 시도로 보여 계정이
제한될 수 있다. 감지한 날짜를 파일에 남기고, 그날은 카카오 OAuth를 타지 않는다.

풀리는 조건: 날짜가 바뀌거나, 사람이 로그인에 성공해 clear()가 불리거나.
기록이 손상됐으면 차단으로 보지 않는다 — 차단 파일 때문에 발행이 영영 멈추면 안 된다.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class LoginChallengeGuard:
    def __init__(self, path: str | Path, today: Callable[[], date] = date.today):
        self._path = Path(path)
        self._today = today

    def is_blocked(self) -> bool:
        """오늘 캡차가 감지돼 자동 로그인을 멈춰야 하는가."""
        return self._blocked_on() == self._today().isoformat()

    def block(self, reason: str) -> bool:
        """오늘 날짜로 차단을 기록한다. 오늘 처음 차단했으면 True(=알릴 일)."""
        newly = not self.is_blocked()
        record = {"blocked_on": self._today().isoformat(), "reason": reason}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            logger.error(f"캡차 차단 기록 실패 — 같은 날 재시도를 막지 못할 수 있음: {e}")
        return newly

    def clear(self) -> None:
        """사람이 로그인에 성공했다 — 오늘 남은 자동 실행을 다시 허용한다."""
        try:
            self._path.unlink()
            logger.info("카카오 캡차 차단 해제")
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning(f"캡차 차단 해제 실패: {e}")

    def _blocked_on(self) -> str:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ""
        except (OSError, ValueError) as e:
            logger.warning(f"캡차 차단 기록을 읽지 못함 (차단 안 함): {e}")
            return ""
        if not isinstance(raw, dict):
            return ""
        return str(raw.get("blocked_on", ""))
