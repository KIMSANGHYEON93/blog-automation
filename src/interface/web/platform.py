"""대시보드 플랫폼별 조립 값 — 티스토리(기본)와 네이버.

네이버는 같은 스프레드시트의 별도 탭을 쓰고, 계정 제재 위험 때문에 하루 1건만 발행한다.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from src.application.use_cases.publish_selected_post import (
    LOGIN_FAILED,
    ManualPublishOutcome,
    ManualPublishResult,
)
from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.notification_port import NotificationPort
from src.domain.ports.pipeline_lock_port import PipelineLockPort
from src.domain.services.quota_manager import DEFAULT_DAILY_LIMIT
from src.domain.value_objects.credentials import Credentials
from src.domain.value_objects.site_profile import SiteProfile
from src.infrastructure.browser.naver.adapter import DEFAULT_PROFILE_DIR, NaverBrowserAdapter
from src.infrastructure.browser.naver.images import pollinations_image_fn, title_thumbnail
from src.infrastructure.browser.selenium_adapter import SeleniumBrowserAdapter
from src.infrastructure.config import Config
from src.infrastructure.notification.null_adapter import NullNotificationAdapter
from src.infrastructure.notification.telegram_adapter import TelegramNotificationAdapter

NAVER_DAILY_LIMIT = 1
PORTAL_NAME = "통합 블로그 포탈"  # 헤더·탭 제목·로그인 화면 이름 — 블로그 구분은 상단 탭이 한다


@dataclass(frozen=True)
class PlatformProfile:
    name: str
    label: str
    worksheet: str
    daily_limit: int
    relogin_label: str = "다시 로그인"
    approve_hint: str = "휴대폰에서 로그인 요청을 승인하세요."


def resolve_platform(name: str, config: Config) -> PlatformProfile:
    if name == "tistory":
        return PlatformProfile(
            "tistory", PORTAL_NAME, "", DEFAULT_DAILY_LIMIT, "카카오톡 다시 로그인",
            "카카오톡에서 로그인 요청을 승인하세요.",
        )
    if name == "naver":
        return PlatformProfile(
            "naver", PORTAL_NAME, config.naver_sheet_tab, NAVER_DAILY_LIMIT, "네이버 다시 로그인",
            "폰 네이버 앱에서 로그인을 승인하세요.",
        )
    raise ValueError(f"지원하지 않는 플랫폼: {name} (tistory 또는 naver)")


def make_browser(
    profile: PlatformProfile,
    config: Config,
    project_root: Path,
    notifier: NotificationPort | None,
    site_profile: SiteProfile | None,
    draft_only: bool = False,
) -> BrowserPort:
    """1건 수동 발행용 브라우저 — 다음 발행 대기 없음. draft_only는 임시저장 시험(네이버)."""
    if profile.name == "naver":
        return NaverBrowserAdapter(
            config.naver_blog_id,
            profile_dir=str(project_root / DEFAULT_PROFILE_DIR),
            draft_only=draft_only,  # 기본 False: 대시보드 발행 = 사람이 승인한 공개 발행
            min_delay=0,
            max_delay=0,
            screenshot_dir=str(project_root / "logs" / "naver"),
            image_fn=pollinations_image_fn(os.getenv("POLLINATIONS_API_KEY", "")),
            thumbnail_fn=partial(title_thumbnail, brand=os.getenv("NAVER_THUMBNAIL_BRAND", "")),
        )
    credentials = Credentials(
        kakao_id=config.kakao_id, kakao_pw=config.kakao_pw, tistory_blog=config.tistory_blog,
    )
    return SeleniumBrowserAdapter(
        credentials=credentials,
        headless=config.headless,
        min_delay=0,
        max_delay=0,
        user_data_dir=str(project_root / ".browser_data"),
        site_profile=site_profile,
        # 2FA가 뜨면 브라우저 앞에 사람이 없다 — 즉시 알려야 승인할 수 있다
        notifier=notifier,
        cta_url=config.naver_blog_url,
    )


def naver_notifier(config: Config) -> NotificationPort:
    """네이버 알림 전용 새 봇. 토큰·채팅이 없으면 조용히 버린다(알림은 부가 기능)."""
    if config.naver_telegram_bot_token and config.telegram_chat_id:
        return TelegramNotificationAdapter(
            bot_token=config.naver_telegram_bot_token, chat_id=config.telegram_chat_id,
        )
    return NullNotificationAdapter()


def dashboard_url(env: Mapping[str, str]) -> str:
    hosts = [h.strip() for h in env.get("DASHBOARD_EXTRA_HOSTS", "").split(",") if h.strip()]
    return f"https://{hosts[0]}/" if hosts else ""


def session_expired_message(url: str) -> str:
    message = (
        "네이버 세션 만료 — 대시보드에서 [네이버 다시 로그인]을 누르고 폰 네이버 앱에서 승인하세요"
    )
    return f"{message}\n{url}" if url else message


def notify_if_expired(logged_in: bool, notifier: NotificationPort, url: str) -> bool:
    if logged_in:
        return False
    notifier.send(session_expired_message(url), "WARNING")
    return True


def notify_login_failure(
    result: ManualPublishResult, notifier: NotificationPort, url: str,
) -> None:
    if result.outcome is ManualPublishOutcome.FAILED and result.message.startswith(LOGIN_FAILED):
        notifier.send(session_expired_message(url), "WARNING")


def build_relogin(
    config: Config, project_root: Path, lock: PipelineLockPort,
) -> Callable[[int], ManualPublishResult]:
    """대시보드 작업 종류 'login'. 발행과 같은 브라우저 프로필을 쓰므로 같은 락을 잡는다."""

    def relogin(row_index: int) -> ManualPublishResult:
        if not lock.acquire():
            return ManualPublishResult.rejected(
                row_index, "자동 파이프라인이 실행 중 — 끝난 뒤 다시 시도하세요",
            )
        try:
            adapter = NaverBrowserAdapter(
                config.naver_blog_id,
                profile_dir=str(project_root / DEFAULT_PROFILE_DIR),
                min_delay=0,
                max_delay=0,
            )
            ok, message = adapter.relogin(config.naver_login_id, config.naver_login_pw)
        finally:
            lock.release()
        outcome = ManualPublishOutcome.LOGGED_IN if ok else ManualPublishOutcome.FAILED
        return ManualPublishResult(outcome, row_index, message)

    return relogin


def build_kakao_relogin(
    config: Config,
    project_root: Path,
    lock: PipelineLockPort,
    site_profile: SiteProfile | None,
    notifier: NotificationPort | None,
) -> Callable[[int], ManualPublishResult]:
    """티스토리 탭의 작업 종류 'login'. 저장된 세션을 먼저 쓰고, 죽었을 때만 카카오 승인을 탄다."""
    profile = resolve_platform("tistory", config)

    def relogin(row_index: int) -> ManualPublishResult:
        if not lock.acquire():
            return ManualPublishResult.rejected(
                row_index, "자동 파이프라인이 실행 중 — 끝난 뒤 다시 시도하세요",
            )
        try:
            browser = make_browser(profile, config, project_root, notifier, site_profile)
            browser.start()
            try:
                ok = browser.login()
            finally:
                browser.stop()
        except Exception as e:  # 브라우저 기동·카카오 화면 오류도 화면에 이유를 남긴다
            return ManualPublishResult(
                ManualPublishOutcome.FAILED, row_index,
                f"카카오 로그인 중 오류: {type(e).__name__}: {e}",
            )
        finally:
            lock.release()
        if ok:
            return ManualPublishResult(
                ManualPublishOutcome.LOGGED_IN, row_index,
                "카카오 로그인 성공 — 티스토리 세션을 저장했습니다",
            )
        return ManualPublishResult(
            ManualPublishOutcome.FAILED, row_index,
            "카카오 로그인 실패 — 카카오톡 승인 시간(5분)이 지났거나 계정 확인이 필요합니다",
        )

    return relogin
