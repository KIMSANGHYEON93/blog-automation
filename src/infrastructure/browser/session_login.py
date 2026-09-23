"""저장된 세션 쿠키로 로그인을 건너뛴다.

카카오 OAuth를 타지 않으면 2FA도 뜨지 않는다. 서버 세션이 죽었으면
False를 돌려 정규 로그인 경로로 넘긴다 — 여기서 절대 예외를 올리지 않는다.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_MANAGE_PATH = "/manage/posts"


def try_session_login(sb, blog_name: str, cookies: list[dict]) -> bool:
    """쿠키를 주입하고 관리 페이지 접근으로 유효성을 확인. 성공 시 True."""
    if not cookies:
        return False

    base = f"https://{blog_name}.tistory.com"
    try:
        # add_cookie는 현재 문서의 도메인과 맞아야 하므로 먼저 해당 도메인을 연다.
        sb.open(base)
        time.sleep(1)
        for c in cookies:
            sb.add_cookie(c)

        sb.open(f"{base}{_MANAGE_PATH}")
        time.sleep(2)
        current = sb.get_current_url()
    except Exception as e:
        logger.info(f"세션 복원 실패 (정규 로그인으로 진행): {e}")
        return False

    # 세션이 죽었으면 티스토리가 로그인 페이지로 돌려보낸다.
    if "/auth/login" in current or "accounts.kakao" in current:
        logger.info("저장된 세션 만료 — 정규 로그인 필요")
        return False

    logger.info("저장된 세션으로 로그인 생략 (카카오 OAuth 미경유)")
    return True
