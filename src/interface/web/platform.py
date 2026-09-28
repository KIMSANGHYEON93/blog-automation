"""대시보드 플랫폼별 조립 값 — 티스토리(기본)와 네이버.

네이버는 같은 스프레드시트의 별도 탭을 쓰고, 계정 제재 위험 때문에 하루 1건만 발행한다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.notification_port import NotificationPort
from src.domain.services.quota_manager import DEFAULT_DAILY_LIMIT
from src.domain.value_objects.credentials import Credentials
from src.domain.value_objects.site_profile import SiteProfile
from src.infrastructure.browser.naver.adapter import DEFAULT_PROFILE_DIR, NaverBrowserAdapter
from src.infrastructure.browser.naver.images import pollinations_image_fn, title_thumbnail
from src.infrastructure.browser.selenium_adapter import SeleniumBrowserAdapter
from src.infrastructure.config import Config

NAVER_DAILY_LIMIT = 1


@dataclass(frozen=True)
class PlatformProfile:
    name: str
    label: str
    worksheet: str
    daily_limit: int


def resolve_platform(name: str, config: Config) -> PlatformProfile:
    if name == "tistory":
        return PlatformProfile("tistory", "티스토리 블로그 관리자", "", DEFAULT_DAILY_LIMIT)
    if name == "naver":
        return PlatformProfile(
            "naver", "네이버 블로그 관리자", config.naver_sheet_tab, NAVER_DAILY_LIMIT,
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
    )
