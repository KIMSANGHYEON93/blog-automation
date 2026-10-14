"""관리자 비밀번호 초기화 — `python -m src.interface.web reset-password`.

비밀번호를 잊었을 때 쓰는 기능이라 웹이 아니라 이 Mac의 터미널에서만 돈다
(로그인 없이 열리는 웹 초기화 화면은 그 자체가 공격 경로다).
해시와 함께 세션 시크릿도 새로 만든다 — 세션은 서명 쿠키라 비밀번호만 바꾸면
폰·브라우저에 남은 기존 로그인이 그대로 살아 있다.
"""
from __future__ import annotations

import os
import re
import secrets
import tempfile
from pathlib import Path

from werkzeug.security import generate_password_hash

MIN_PASSWORD_LENGTH = 12
_OWNER_ONLY = 0o600


def set_env_values(text: str, values: dict[str, str]) -> str:
    """KEY=값 줄을 그 자리에서 바꾸고, 없는 키는 끝에 덧붙인다. 나머지 줄은 그대로."""
    pending = dict(values)
    lines = []
    for line in text.splitlines():
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)=", line)
        key = match.group(1) if match else ""
        lines.append(f"{key}={pending.pop(key)}" if key in pending else line)
    lines += [f"{key}={value}" for key, value in pending.items()]
    return "\n".join(lines) + "\n"


def reset_admin_password(env_path: Path, password: str) -> None:
    """해시·세션 시크릿을 바꿔 .env를 원자적으로 다시 쓴다(0600)."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"비밀번호는 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다")
    text = set_env_values(env_path.read_text(encoding="utf-8"), {
        # 해시에 $가 있어 dotenv 변수 치환을 막으려 작은따옴표로 감싼다
        "DASHBOARD_ADMIN_PASSWORD_HASH": f"'{generate_password_hash(password)}'",
        "DASHBOARD_SECRET_KEY": secrets.token_urlsafe(48),
    })
    # 같은 디렉터리의 임시 파일에 쓴 뒤 교체 — 중간에 죽어도 .env가 반쯤 쓰인 채 남지 않는다
    fd, tmp = tempfile.mkstemp(dir=env_path.parent, prefix=".env.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, _OWNER_ONLY)
        os.replace(tmp, env_path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
