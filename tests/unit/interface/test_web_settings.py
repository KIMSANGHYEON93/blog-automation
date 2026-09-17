"""DashboardSettings — 대시보드 실행 환경변수 검증 (fail fast)."""
from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from src.interface.web.settings import DashboardSettings, SettingsError

HASH = generate_password_hash("pw-for-test-only")
SECRET = "k" * 32


def _env(**overrides) -> dict:
    env = {
        "DASHBOARD_ADMIN_USER": "admin",
        "DASHBOARD_ADMIN_PASSWORD_HASH": HASH,
        "DASHBOARD_SECRET_KEY": SECRET,
    }
    env.update(overrides)
    return {k: v for k, v in env.items() if v is not None}


class TestDashboardSettings:
    def test_기본값(self):
        s = DashboardSettings.from_env(_env())
        assert (s.host, s.port, s.admin_user) == ("127.0.0.1", 8787, "admin")
        assert s.secure_cookies is False

    def test_필수값_누락시_이름을_모두_알려줌(self):
        with pytest.raises(SettingsError) as exc:
            DashboardSettings.from_env({})
        message = str(exc.value)
        required = ("DASHBOARD_ADMIN_USER", "DASHBOARD_ADMIN_PASSWORD_HASH", "DASHBOARD_SECRET_KEY")
        for name in required:
            assert name in message

    def test_짧은_시크릿_거부(self):
        with pytest.raises(SettingsError, match="32"):
            DashboardSettings.from_env(_env(DASHBOARD_SECRET_KEY="short"))

    def test_평문_비밀번호는_거부(self):
        with pytest.raises(SettingsError, match="해시"):
            DashboardSettings.from_env(_env(DASHBOARD_ADMIN_PASSWORD_HASH="plain-password"))

    def test_외부_바인딩은_명시적_허용_필요(self):
        with pytest.raises(SettingsError, match="DASHBOARD_ALLOW_REMOTE"):
            DashboardSettings.from_env(_env(DASHBOARD_HOST="0.0.0.0"))
        allowed = _env(
            DASHBOARD_HOST="0.0.0.0",
            DASHBOARD_ALLOW_REMOTE="true",
            DASHBOARD_SECURE_COOKIES="true",
        )
        assert DashboardSettings.from_env(allowed).host == "0.0.0.0"

    def test_외부_바인딩은_Secure_쿠키_필수(self):
        insecure = _env(DASHBOARD_HOST="0.0.0.0", DASHBOARD_ALLOW_REMOTE="true")
        with pytest.raises(SettingsError, match="DASHBOARD_SECURE_COOKIES"):
            DashboardSettings.from_env(insecure)

    def test_허용_Host는_루프백_주소와_포트(self):
        hosts = DashboardSettings.from_env(_env(DASHBOARD_PORT="8799")).allowed_hosts
        assert {"127.0.0.1:8799", "localhost:8799"} <= hosts
        assert "evil.example:8799" not in hosts

    def test_외부_바인딩은_Host_검사를_프록시에_맡김(self):
        remote = _env(
            DASHBOARD_HOST="0.0.0.0",
            DASHBOARD_ALLOW_REMOTE="true",
            DASHBOARD_SECURE_COOKIES="true",
        )
        assert DashboardSettings.from_env(remote).allowed_hosts is None

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
    def test_루프백은_허용(self, host):
        assert DashboardSettings.from_env(_env(DASHBOARD_HOST=host)).host == host

    def test_잘못된_포트(self):
        with pytest.raises(SettingsError, match="DASHBOARD_PORT"):
            DashboardSettings.from_env(_env(DASHBOARD_PORT="http"))
        with pytest.raises(SettingsError, match="DASHBOARD_PORT"):
            DashboardSettings.from_env(_env(DASHBOARD_PORT="70000"))

    def test_secure_cookie_옵션(self):
        settings = DashboardSettings.from_env(_env(DASHBOARD_SECURE_COOKIES="true"))
        assert settings.secure_cookies is True
