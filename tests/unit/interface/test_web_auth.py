"""관리자 인증 — 비밀번호 해시 검증 + 로그인 시도 제한."""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from src.interface.web.auth import AdminAuthenticator, LoginThrottle


class FakeClock:
    def __init__(self, now: float = 1_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def _auth() -> AdminAuthenticator:
    return AdminAuthenticator(username="admin", password_hash=generate_password_hash("s3cret-pass"))


class TestAdminAuthenticator:
    def test_올바른_계정(self):
        assert _auth().verify("admin", "s3cret-pass") is True

    def test_잘못된_비밀번호(self):
        assert _auth().verify("admin", "wrong") is False

    def test_잘못된_사용자명(self):
        assert _auth().verify("root", "s3cret-pass") is False

    def test_빈_입력(self):
        assert _auth().verify("", "") is False


class TestLoginThrottle:
    def test_허용_횟수_이내는_통과(self):
        throttle = LoginThrottle(max_attempts=3, window_seconds=60, clock=FakeClock())
        for _ in range(2):
            throttle.record_failure("1.2.3.4")
        assert throttle.is_blocked("1.2.3.4") is False

    def test_허용_횟수_초과시_차단_다른_IP는_영향없음(self):
        throttle = LoginThrottle(max_attempts=3, window_seconds=60, clock=FakeClock())
        for _ in range(3):
            throttle.record_failure("1.2.3.4")
        assert throttle.is_blocked("1.2.3.4") is True
        assert throttle.is_blocked("5.6.7.8") is False

    def test_시간창이_지나면_차단_해제(self):
        clock = FakeClock()
        throttle = LoginThrottle(max_attempts=3, window_seconds=60, clock=clock)
        for _ in range(3):
            throttle.record_failure("1.2.3.4")
        clock.now += 61
        assert throttle.is_blocked("1.2.3.4") is False

    def test_성공하면_실패_기록_초기화(self):
        throttle = LoginThrottle(max_attempts=3, window_seconds=60, clock=FakeClock())
        for _ in range(2):
            throttle.record_failure("1.2.3.4")
        throttle.reset("1.2.3.4")
        throttle.record_failure("1.2.3.4")
        assert throttle.is_blocked("1.2.3.4") is False
