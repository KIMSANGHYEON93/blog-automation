"""관리자 비밀번호 초기화 — .env의 해시를 바꾸고 세션 시크릿도 갈아 기존 로그인을 끊는다."""
from __future__ import annotations

import os
import stat

import pytest
from werkzeug.security import check_password_hash

from src.interface.web.password_reset import reset_admin_password, set_env_values

ENV = (
    "# 대시보드\n"
    "DASHBOARD_ADMIN_USER=admin\n"
    "DASHBOARD_ADMIN_PASSWORD_HASH='scrypt:old$hash'\n"
    "DASHBOARD_SECRET_KEY=old-secret\n"
    "KAKAO_PW=keep-me\n"
)


def _read_env(path) -> dict[str, str]:
    pairs = (line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    return {k: v.strip("'") for k, v in pairs}


def test_있는_키는_그_자리에서_바꾸고_없는_키는_덧붙인다():
    text = set_env_values(ENV, {"DASHBOARD_SECRET_KEY": "new", "NEW_KEY": "x"})
    assert "DASHBOARD_SECRET_KEY=new\n" in text
    assert "old-secret" not in text
    assert text.startswith("# 대시보드\nDASHBOARD_ADMIN_USER=admin\n")
    assert text.endswith("NEW_KEY=x\n")
    assert "KAKAO_PW=keep-me" in text


def test_초기화하면_새_비밀번호로만_로그인되고_시크릿이_바뀐다(tmp_path):
    env = tmp_path / ".env"
    env.write_text(ENV)
    os.chmod(env, 0o644)

    reset_admin_password(env, "new-password-1234")

    values = _read_env(env)
    assert check_password_hash(values["DASHBOARD_ADMIN_PASSWORD_HASH"], "new-password-1234")
    assert values["DASHBOARD_SECRET_KEY"] not in ("", "old-secret")
    assert values["KAKAO_PW"] == "keep-me"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600  # 자격증명 파일 — 소유자만


def test_짧은_비밀번호는_거부하고_파일을_건드리지_않는다(tmp_path):
    env = tmp_path / ".env"
    env.write_text(ENV)
    with pytest.raises(ValueError):
        reset_admin_password(env, "short")
    assert env.read_text() == ENV
