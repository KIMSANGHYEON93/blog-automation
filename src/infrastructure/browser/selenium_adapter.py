"""SeleniumBrowserAdapter — BrowserPort implementation using SeleniumBase."""
from __future__ import annotations

import logging
import random
import time

from src.domain.entities.post import Post
from src.domain.ports.browser_port import BrowserPort
from src.domain.value_objects.credentials import Credentials
from src.domain.value_objects.publish_result import PublishResult
from src.domain.value_objects.site_profile import SiteProfile
from src.infrastructure.browser.kakao_auth import kakao_login
from src.infrastructure.browser.tistory_editor import publish_post, update_post

logger = logging.getLogger(__name__)


class SeleniumBrowserAdapter(BrowserPort):
    def __init__(self, credentials: Credentials, headless: bool = True,
                 min_delay: int = 300, max_delay: int = 900,
                 user_data_dir: str = "",
                 site_profile: SiteProfile | None = None):
        self._credentials = credentials
        self._headless = headless
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._user_data_dir = user_data_dir
        self._site_profile = site_profile
        self._sb = None
        self._sb_context = None  # SB 컨텍스트 매니저 참조 유지

    def start(self) -> None:
        import os

        from seleniumbase import SB
        # 쿠키 영속화: user_data_dir 설정 시 브라우저 세션 유지 (2FA 1회만)
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
        return kakao_login(
            self._sb,
            self._credentials.kakao_id,
            self._credentials.kakao_pw,
        )

    def publish(self, post: Post) -> PublishResult:
        result = publish_post(
            self._sb, post, self._credentials.tistory_blog,
            profile=self._site_profile,
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
        )
        delay = random.randint(self._min_delay, self._max_delay)
        logger.info(f"다음 수정까지 {delay}초 대기")
        time.sleep(delay)
        return result
