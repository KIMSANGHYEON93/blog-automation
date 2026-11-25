"""SeleniumBrowserAdapter — BrowserPort implementation using SeleniumBase."""
from __future__ import annotations

import contextlib
import html
import logging
import random
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from src.domain.entities.post import Post
from src.domain.exceptions import LoginBlockedError, LoginChallengeError
from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.notification_port import NotificationPort
from src.domain.value_objects.credentials import Credentials
from src.domain.value_objects.publish_result import PublishResult
from src.domain.value_objects.site_profile import SiteProfile
from src.infrastructure.browser.kakao_auth import kakao_login
from src.infrastructure.browser.login_challenge_guard import LoginChallengeGuard
from src.infrastructure.browser.session_login import try_session_login
from src.infrastructure.browser.session_store import SessionStore
from src.infrastructure.browser.tistory_editor import publish_post, update_post

logger = logging.getLogger(__name__)

# .browser_data/ 아래에 둔다 — .gitignore에 이미 걸려 있다.
SESSION_FILENAME = "tistory_session.json"
# 카카오 보안문제(캡차)가 뜬 날짜 — 그날은 자동 로그인을 하지 않는다
CHALLENGE_BLOCK_FILENAME = "kakao_challenge_block.json"
MANUAL_LOGIN_HINT = (
    "사람이 보이는 창에서 로그인하세요: .venv/bin/python scripts/tistory_login.py"
)


class SeleniumBrowserAdapter(BrowserPort):
    def __init__(self, credentials: Credentials, headless: bool = True,
                 min_delay: int = 300, max_delay: int = 900,
                 user_data_dir: str = "",
                 site_profile: SiteProfile | None = None,
                 notifier: NotificationPort | None = None,
                 cta_url: str = "",
                 today: Callable[[], date] = date.today):
        # notifier: 카카오 2FA 감지 시 즉시 알리기 위한 채널. 없으면 조용히 진행.
        self._notifier = notifier
        self._credentials = credentials
        self._headless = headless
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._user_data_dir = user_data_dir
        self._site_profile = site_profile
        self._cta_url = cta_url  # 티스토리 글 끝 네이버 이웃 CTA 주소 — 비면 붙이지 않는다
        self._sb: Any = None  # SeleniumBase SB — 타입 정보 없음
        self._sb_context: Any = None  # SB 컨텍스트 매니저 참조 유지
        self._today = today  # 캡차 당일 차단의 '오늘' — 테스트에서 바꿔 끼운다

    def start(self) -> None:
        import os

        from seleniumbase import SB
        # 쿠키 영속화: user_data_dir 설정 시 브라우저 세션 유지 (2FA 1회만)
        try:
            if self._user_data_dir:
                abs_path = os.path.abspath(self._user_data_dir)
                os.makedirs(abs_path, exist_ok=True)
                self._sb_context = SB(
                    headless=self._headless,
                    chromium_arg=f"--user-data-dir={abs_path}",
                )
            else:
                self._sb_context = SB(headless=self._headless)
            assert self._sb_context is not None
            self._sb = self._sb_context.__enter__()
            logger.info("브라우저 시작")
        except Exception as e:
            logger.error(f"브라우저 시작 실패: {e}")
            self._cleanup_zombie_drivers()
            self._sb = None
            self._sb_context = None
            raise

    def stop(self) -> None:
        if self._sb_context:
            try:
                self._sb_context.__exit__(None, None, None)
                logger.info("브라우저 종료")
            except Exception as e:
                logger.warning(f"브라우저 종료 중 오류 (무시): {e}")
            finally:
                self._cleanup_zombie_drivers()
                self._sb = None
                self._sb_context = None

    def _cleanup_zombie_drivers(self) -> None:
        """user-data-dir 기반으로 잔존 Chrome/ChromeDriver 프로세스 정리."""
        import os
        import subprocess

        if not self._user_data_dir:
            return
        abs_path = os.path.abspath(self._user_data_dir)
        try:
            result = subprocess.run(
                ["pgrep", "-f", f"user-data-dir={abs_path}"],
                capture_output=True, text=True, timeout=5,
            )
            pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
            if pids:
                subprocess.run(["kill"] + pids, capture_output=True, timeout=5)
                logger.info(f"잔존 브라우저 프로세스 정리: {len(pids)}건")
        except Exception:
            pass

    def login(self) -> bool:
        """저장된 세션을 먼저 쓰고, 죽었을 때만 카카오 OAuth를 탄다.

        매 실행이 OAuth를 다시 타면 로그인 횟수가 실행 횟수와 같아지고
        카카오 이상탐지가 2FA를 띄운다(2026-09-23 실측: 기동 7회에 2FA 3회).

        카카오가 보안문제(캡차)를 띄우면 그날은 OAuth를 다시 타지 않는다
        (LoginBlockedError). 알림은 처음 감지할 때 한 번만 보낸다.
        """
        blog = self._credentials.tistory_blog
        store = self._session_store()
        guard = self._challenge_guard()
        if try_session_login(self._sb, blog, store.load()):
            guard.clear()  # 세션이 살아 있다 = 사람이 로그인해 남긴 세션일 수 있다
            return True
        store.clear()

        if guard.is_blocked():
            logger.warning("오늘 카카오 보안문제(캡차)가 감지돼 자동 로그인을 건너뜀")
            raise LoginBlockedError(
                f"오늘 카카오 보안문제(캡차)가 감지돼 자동 로그인을 건너뜀 — {MANUAL_LOGIN_HINT}"
            )

        try:
            ok = kakao_login(
                self._sb,
                self._credentials.kakao_id,
                self._credentials.kakao_pw,
                notifier=self._notifier,
            )
        except LoginChallengeError as e:
            if guard.block(str(e)):
                self._notify_challenge(str(e))
            raise
        if ok:
            # 다음 실행이 OAuth를 건너뛰도록 세션을 남긴다.
            with contextlib.suppress(Exception):
                store.save(self._sb.get_cookies())
            guard.clear()
        return ok

    def adopt_manual_login(self) -> bool:
        """사람이 이 브라우저에서 직접 로그인한 결과를 확인하고 세션으로 남긴다.

        자격증명을 입력하지 않는다 — 캡차는 사람이 푼다(scripts/tistory_login.py).
        관리 페이지가 열리면 세션을 저장하고 당일 차단을 푼다.
        """
        blog = self._credentials.tistory_blog
        self._sb.open(f"https://{blog}.tistory.com/manage/posts")
        time.sleep(2)
        current = str(self._sb.get_current_url())
        if "/auth/login" in current or "accounts.kakao" in current:
            logger.warning("수동 로그인이 확인되지 않음 — 관리 페이지가 로그인 화면으로 돌아감")
            return False
        self._session_store().save(self._sb.get_cookies())
        self._challenge_guard().clear()
        logger.info("수동 로그인 확인 — 세션 저장, 캡차 차단 해제")
        return True

    def _notify_challenge(self, detail: str) -> None:
        """캡차 감지를 사람에게 알린다. 알림 실패가 차단 기록을 깨면 안 된다."""
        if self._notifier is None:
            return
        when = f"{self._today().isoformat()} {datetime.now():%H:%M}"
        message = (
            f"티스토리({self._credentials.tistory_blog}) 카카오 보안문제(캡차) 감지 — {when}\n"
            "오늘은 자동 로그인(발행·수정·복구·대시보드)을 멈춥니다. 내일 다시 시도합니다.\n"
            f"지금 풀려면 {MANUAL_LOGIN_HINT}\n"
            f"화면: {html.escape(detail)}"
        )
        try:
            self._notifier.send(message, level="ERROR")
        except Exception as e:
            logger.warning(f"캡차 알림 전송 실패 (차단은 유지): {e}")

    def _challenge_guard(self) -> LoginChallengeGuard:
        base = self._user_data_dir or "."
        return LoginChallengeGuard(Path(base) / CHALLENGE_BLOCK_FILENAME, today=self._today)

    def _session_store(self) -> SessionStore:
        base = self._user_data_dir or "."
        return SessionStore(Path(base) / SESSION_FILENAME)

    def publish(self, post: Post) -> PublishResult:
        result = publish_post(
            self._sb, post, self._credentials.tistory_blog,
            profile=self._site_profile,
            cta_url=self._cta_url,
        )
        # 건별 딜레이 (봇 탐지 회피)
        delay = random.randint(self._min_delay, self._max_delay)
        logger.info(f"다음 발행까지 {delay}초 대기")
        time.sleep(delay)
        return result

    def update(self, post: Post) -> PublishResult:
        result = update_post(
            self._sb, post, self._credentials.tistory_blog,
            profile=self._site_profile,
            cta_url=self._cta_url,
        )
        delay = random.randint(self._min_delay, self._max_delay)
        logger.info(f"다음 수정까지 {delay}초 대기")
        time.sleep(delay)
        return result
