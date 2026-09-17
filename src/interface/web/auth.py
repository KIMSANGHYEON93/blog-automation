"""관리자 인증 — 단일 관리자 계정(비밀번호 해시) + IP별 로그인 시도 제한."""
from __future__ import annotations

import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Callable

from werkzeug.security import check_password_hash, generate_password_hash

# 존재하지 않는 사용자명에도 실제 해시 비교를 수행해 응답 시간으로 계정 유무가 드러나지 않게 함
_DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(16))


class AdminAuthenticator:
    def __init__(self, username: str, password_hash: str):
        if not username or not password_hash:
            raise ValueError("관리자 사용자명과 비밀번호 해시가 필요합니다")
        self._username = username
        self._password_hash = password_hash

    def verify(self, username: str, password: str) -> bool:
        name_ok = hmac.compare_digest((username or "").encode(), self._username.encode())
        target_hash = self._password_hash if name_ok else _DUMMY_HASH
        try:
            password_ok = check_password_hash(target_hash, password or "")
        except ValueError:
            password_ok = False
        return name_ok and password_ok


class LoginThrottle:
    """window_seconds 동안 max_attempts번 실패한 IP는 차단."""

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 15 * 60,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._mutex = threading.Lock()

    def is_blocked(self, client: str) -> bool:
        with self._mutex:
            return len(self._recent(client)) >= self._max_attempts

    def record_failure(self, client: str) -> None:
        with self._mutex:
            self._recent(client).append(self._clock())

    def reset(self, client: str) -> None:
        with self._mutex:
            self._failures.pop(client, None)

    def _recent(self, client: str) -> deque[float]:
        attempts = self._failures[client]
        cutoff = self._clock() - self._window
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        return attempts
