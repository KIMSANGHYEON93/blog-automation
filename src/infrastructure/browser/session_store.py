"""SessionStore — 티스토리 세션 쿠키를 디스크에 보존한다.

왜 필요한가: 티스토리 세션 쿠키(__T_, __T_SECURE)는 세션 쿠키라 브라우저를
닫으면 사라진다. 매 실행이 카카오 OAuth를 다시 타므로 로그인 횟수가 실행 횟수와
같아지고, 카카오 이상탐지가 그 빈도에 반응해 2FA를 띄운다
(2026-09-23 실측: 브라우저 기동 7회에 2FA 3회).

쿠키를 보존했다가 주입하면 서버 세션이 살아 있는 동안 로그인을 건너뛴다.

보안: 쿠키는 인증 자격증명이다. 티스토리 도메인 것만 담고(카카오 _kau는 제외),
파일은 소유자만 읽도록 0600으로 쓴다. 저장 위치는 .browser_data/ 아래라
.gitignore에 이미 걸려 있다.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_OWNER_ONLY = 0o600

# 카카오 트래킹(tiara)은 로그인과 무관하고, 카카오 계정 쿠키(_kau)는
# 유출 시 피해가 훨씬 크므로 담지 않는다.
_EXCLUDED_DOMAIN_PARTS = ("kakao.com", "tiara.")


def is_tistory_cookie(cookie: dict) -> bool:
    """로그인 세션 복원에 필요한 티스토리 쿠키인가."""
    domain = str(cookie.get("domain", "")).lower()
    if not domain or "tistory.com" not in domain:
        return False
    return not any(part in domain for part in _EXCLUDED_DOMAIN_PARTS)


def strip_expired(cookies: list[dict], now: int) -> list[dict]:
    """만료된 쿠키 제거. expiry가 없으면 세션 쿠키라 남긴다."""
    alive = []
    for c in cookies:
        expiry = c.get("expiry") or c.get("expires")
        if expiry is not None and int(expiry) <= now:
            continue
        alive.append(c)
    return alive


class SessionStore:
    def __init__(self, path: str | Path):
        self._path = Path(path)

    def save(self, cookies: list[dict]) -> int:
        """티스토리 쿠키만 골라 0600으로 저장. 저장 건수 반환."""
        keep = [c for c in cookies if is_tistory_cookie(c)]
        if not keep:
            logger.debug("저장할 티스토리 쿠키 없음")
            return 0
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # 권한을 먼저 좁힌 뒤 내용을 쓴다 — 넓은 권한으로 존재하는 순간이 없도록.
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _OWNER_ONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(keep, f, ensure_ascii=False)
        os.chmod(self._path, _OWNER_ONLY)  # 기존 파일이었다면 권한을 다시 조인다
        logger.info(f"티스토리 세션 저장: {len(keep)}건 → {self._path.name}")
        return len(keep)

    def load(self) -> list[dict]:
        """저장된 쿠키. 없거나 손상됐으면 빈 리스트(=재로그인)."""
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.warning(f"세션 파일 읽기 실패 (재로그인): {e}")
            return []
        if not isinstance(raw, list):
            return []
        return strip_expired(raw, now=int(time.time()))

    def clear(self) -> None:
        """세션 폐기. 유효성 검증에 실패했을 때 부른다."""
        try:
            self._path.unlink()
            logger.info("저장된 티스토리 세션 폐기")
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"세션 파일 삭제 실패: {e}")
