"""티스토리 수동 로그인 — 카카오 보안문제(캡차)가 떠서 자동 로그인이 멈췄을 때.

사용법 (저장소 루트에서):
    .venv/bin/python scripts/tistory_login.py

보이는 크롬 창이 티스토리 로그인 화면을 연다. 사람이 직접 카카오 로그인을 하고
(보안문제·2단계 인증 포함, '로그인 상태 유지' 체크) 터미널에서 Enter를 누르면
관리 페이지 접근으로 로그인을 확인한 뒤 세션(.browser_data/tistory_session.json)을
저장하고 당일 캡차 차단(.browser_data/kakao_challenge_block.json)을 푼다.

이 스크립트는 아이디·비밀번호를 입력하지 않는다 — 캡차를 자동으로 풀거나 우회하지 않는다.
자동 실행과 같은 .browser_data를 쓰므로 발행과 같은 락을 잡는다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# `python scripts/tistory_login.py`로 실행하면 sys.path에 scripts/만 들어가 src를 못 찾는다
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.value_objects.credentials import Credentials  # noqa: E402
from src.infrastructure.browser.kakao_auth import TISTORY_LOGIN_URL  # noqa: E402
from src.infrastructure.browser.selenium_adapter import SeleniumBrowserAdapter  # noqa: E402
from src.infrastructure.locking.directory_lock import DirectoryPipelineLock  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

LOCK_DIR = PROJECT_ROOT / ".pipeline_b.lock"  # 자동 발행·대시보드와 같은 락
BROWSER_DATA = PROJECT_ROOT / ".browser_data"


def main() -> int:
    blog = os.getenv("TISTORY_BLOG", "").strip()
    if not blog:
        print(".env에 TISTORY_BLOG를 넣어 주세요.")
        return 1

    lock = DirectoryPipelineLock(LOCK_DIR)
    if not lock.acquire():
        print("자동 실행이나 대시보드 작업이 브라우저를 쓰는 중입니다. 끝난 뒤 다시 실행하세요.")
        return 1

    # 자격증명은 비워 둔다 — 이 스크립트는 입력하지 않는다
    adapter = SeleniumBrowserAdapter(
        Credentials(kakao_id="", kakao_pw="", tistory_blog=blog),
        headless=False,
        min_delay=0,
        max_delay=0,
        user_data_dir=str(BROWSER_DATA),
    )
    try:
        adapter.start()
        adapter._sb.open(TISTORY_LOGIN_URL)
        print("열린 창에서 '카카오계정으로 로그인'으로 직접 로그인하세요.")
        print("보안문제·2단계 인증도 직접 풀고, '로그인 상태 유지'를 체크하세요.")
        input("티스토리 화면이 보이면 Enter ▶ ")
        ok = adapter.adopt_manual_login()
    finally:
        adapter.stop()
        lock.release()

    if ok:
        print("로그인 확인 — 세션을 저장하고 오늘의 자동 로그인 차단을 풀었습니다.")
        return 0
    print("로그인이 확인되지 않았습니다. 다시 실행해 로그인하세요.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
