"""DashboardSettings — 관리자 대시보드 환경변수 (시작 시 검증, 누락/약한 설정은 즉시 실패)."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

REQUIRED = ("DASHBOARD_ADMIN_USER", "DASHBOARD_ADMIN_PASSWORD_HASH", "DASHBOARD_SECRET_KEY")
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
MIN_SECRET_LENGTH = 32
# werkzeug generate_password_hash 형식: "<method>:<params>$<salt>$<hash>"
HASH_PREFIXES = ("scrypt:", "pbkdf2:")


class SettingsError(ValueError):
    pass


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class DashboardSettings:
    admin_user: str
    admin_password_hash: str
    secret_key: str
    host: str = "127.0.0.1"
    port: int = 8787
    secure_cookies: bool = False

    @property
    def allowed_hosts(self) -> frozenset[str] | None:
        """로컬 바인딩이면 Host 헤더 허용 목록 (DNS rebinding 방지). 외부 바인딩은 프록시가 담당."""
        if self.host not in LOOPBACK_HOSTS:
            return None
        return frozenset({f"127.0.0.1:{self.port}", f"localhost:{self.port}", f"[::1]:{self.port}"})

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> DashboardSettings:
        missing = [name for name in REQUIRED if not env.get(name, "").strip()]
        if missing:
            raise SettingsError(
                f"필수 환경 변수 누락: {', '.join(missing)} "
                "(python -m src.interface.web hash-password 로 해시 생성)"
            )
        secret = env["DASHBOARD_SECRET_KEY"].strip()
        if len(secret) < MIN_SECRET_LENGTH:
            raise SettingsError(f"DASHBOARD_SECRET_KEY는 {MIN_SECRET_LENGTH}자 이상이어야 합니다")
        password_hash = env["DASHBOARD_ADMIN_PASSWORD_HASH"].strip()
        if not password_hash.startswith(HASH_PREFIXES) or password_hash.count("$") != 2:
            raise SettingsError(
                "DASHBOARD_ADMIN_PASSWORD_HASH에는 평문이 아닌 비밀번호 해시를 넣어야 합니다",
            )
        host = env.get("DASHBOARD_HOST", "127.0.0.1").strip() or "127.0.0.1"
        secure_cookies = _truthy(env.get("DASHBOARD_SECURE_COOKIES", ""))
        if host not in LOOPBACK_HOSTS:
            _validate_remote(host, env, secure_cookies)
        return cls(
            admin_user=env["DASHBOARD_ADMIN_USER"].strip(),
            admin_password_hash=password_hash,
            secret_key=secret,
            host=host,
            port=_parse_port(env.get("DASHBOARD_PORT", "8787")),
            secure_cookies=secure_cookies,
        )


def _validate_remote(host: str, env: Mapping[str, str], secure_cookies: bool) -> None:
    if not _truthy(env.get("DASHBOARD_ALLOW_REMOTE", "")):
        raise SettingsError(
            f"{host}에 바인딩하면 로그인 정보가 암호화 없이 네트워크로 전송됩니다. "
            "HTTPS 리버스 프록시 뒤에서만 DASHBOARD_ALLOW_REMOTE=true로 허용하세요",
        )
    if not secure_cookies:
        raise SettingsError(
            "외부 바인딩(HTTPS 프록시 뒤)에서는 DASHBOARD_SECURE_COOKIES=true가 필요합니다",
        )


def _parse_port(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError:
        raise SettingsError(f"DASHBOARD_PORT가 숫자가 아님: {raw!r}") from None
    if not 1 <= port <= 65535:
        raise SettingsError(f"DASHBOARD_PORT 범위 오류: {port}")
    return port
