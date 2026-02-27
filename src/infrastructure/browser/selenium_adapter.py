"""SeleniumBrowserAdapter — BrowserPort implementation using SeleniumBase."""
import logging
import time
import random

from src.domain.entities.post import Post
from src.domain.ports.browser_port import BrowserPort
from src.domain.value_objects.credentials import Credentials
from src.domain.value_objects.publish_result import PublishResult
from src.infrastructure.browser.kakao_auth import kakao_login
from src.infrastructure.browser.tistory_editor import publish_post

logger = logging.getLogger(__name__)


class SeleniumBrowserAdapter(BrowserPort):
    def __init__(self, credentials: Credentials, headless: bool = True,
                 min_delay: int = 300, max_delay: int = 900):
        self._credentials = credentials
        self._headless = headless
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._sb = None

    def start(self) -> None:
        from seleniumbase import SB
        self._sb = SB(headless=self._headless).__enter__()
        logger.info("브라우저 시작")

    def stop(self) -> None:
        if self._sb:
            try:
                self._sb.__exit__(None, None, None)
                logger.info("브라우저 종료")
            except Exception as e:
                logger.warning(f"브라우저 종료 중 오류 (무시): {e}")
            finally:
                self._sb = None

    def login(self) -> bool:
        return kakao_login(
            self._sb,
            self._credentials.kakao_id,
            self._credentials.kakao_pw,
        )

    def publish(self, post: Post) -> PublishResult:
        result = publish_post(self._sb, post, self._credentials.tistory_blog)
        # 건별 딜레이 (봇 탐지 회피)
        delay = random.randint(self._min_delay, self._max_delay)
        logger.info(f"다음 발행까지 {delay}초 대기")
        time.sleep(delay)
        return result
