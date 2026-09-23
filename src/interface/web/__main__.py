"""관리자 대시보드 Composition Root.

    python -m src.interface.web hash-password   # 관리자 비밀번호 해시 생성
    python -m src.interface.web gen-secret      # 세션 시크릿 생성
    python -m src.interface.web                 # 대시보드 실행 (기본 http://127.0.0.1:8787)
    python -m src.interface.web --platform naver  # 네이버 대시보드 (naver_calendar 탭)
"""
from __future__ import annotations

import argparse
import getpass
import logging
import os
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.application.use_cases.list_posts import ListPostsUseCase
from src.application.use_cases.publish_selected_post import (
    ManualPublishResult,
    PublishSelectedPostUseCase,
)
from src.domain.services.internal_link_service import InternalLinkService
from src.domain.services.quota_manager import QuotaManager
from src.domain.value_objects.site_profile import SiteProfile
from src.infrastructure.browser.tistory_editor import set_site_profile
from src.infrastructure.config import Config
from src.infrastructure.locking.directory_lock import DirectoryPipelineLock
from src.infrastructure.logging_setup import setup_logging
from src.infrastructure.persistence.google_sheets_repo import GoogleSheetsPostRepository
from src.infrastructure.persistence.json_site_profile import JsonSiteProfileAdapter
from src.interface.cli import _build_notification as build_notification
from src.interface.web.app import create_app
from src.interface.web.auth import AdminAuthenticator
from src.interface.web.jobs import PublishJobRunner
from src.interface.web.platform import PlatformProfile, make_browser, resolve_platform
from src.interface.web.settings import DashboardSettings, SettingsError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOCK_DIR = PROJECT_ROOT / ".pipeline_b.lock"  # run_pipeline_b.sh와 같은 락
LOG_FILE = PROJECT_ROOT / "logs" / "dashboard-web.log"
MIN_PASSWORD_LENGTH = 12

logger = logging.getLogger(__name__)


def _hash_password() -> int:
    password = getpass.getpass("관리자 비밀번호: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"비밀번호는 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다", file=sys.stderr)
        return 1
    if password != getpass.getpass("비밀번호 확인: "):
        print("비밀번호가 일치하지 않습니다", file=sys.stderr)
        return 1
    print("\n.env에 추가하세요 ($ 문자가 있으므로 작은따옴표로 감쌀 것):")
    print(f"DASHBOARD_ADMIN_PASSWORD_HASH='{generate_password_hash(password)}'")
    return 0


def _load_site_profile(config: Config) -> SiteProfile | None:
    path = PROJECT_ROOT / config.site_profile_path
    if not path.exists():
        return None
    profile = JsonSiteProfileAdapter(path).load()
    set_site_profile(profile)  # tistory_editor 카테고리 해석용 (cli.py와 동일)
    return profile


def _build_publisher(  # type: ignore[no-untyped-def]
    config: Config, repo: GoogleSheetsPostRepository, profile: PlatformProfile,
):
    # 티스토리 카테고리 해석용 프로필은 티스토리에서만 읽는다 (cli.py와 동일)
    site_profile = _load_site_profile(config) if profile.name == "tistory" else None

    def publish(row_index: int) -> ManualPublishResult:
        use_case = PublishSelectedPostUseCase(
            repo=repo,
            browser=make_browser(
                profile, config, PROJECT_ROOT, build_notification(), site_profile,
            ),
            enricher=InternalLinkEnricher(InternalLinkService()),
            quota=QuotaManager(daily_limit=profile.daily_limit),
            lock=DirectoryPipelineLock(LOCK_DIR),
        )
        logger.info(f"[{profile.name}] 수동 발행 시작: row={row_index}")
        result = use_case.execute(row_index)
        logger.info(
            f"[{profile.name}] 수동 발행 결과: row={row_index} "
            f"{result.outcome.value} — {result.message}"
        )
        return result

    return publish


def _serve(platform: str) -> int:
    try:
        settings = DashboardSettings.from_env(os.environ)
    except SettingsError as e:
        print(f"대시보드 설정 오류: {e}", file=sys.stderr)
        return 2

    config = Config.from_env()
    profile = resolve_platform(platform, config)
    if profile.name == "naver":
        config.validate_naver()
    else:
        config.validate()
    repo = GoogleSheetsPostRepository(
        creds_path=config.google_creds, sheet_name=config.sheet_name,
        worksheet=profile.worksheet,
    )
    app = create_app(
        authenticator=AdminAuthenticator(settings.admin_user, settings.admin_password_hash),
        list_posts=ListPostsUseCase(repo),
        job_runner=PublishJobRunner(publish=_build_publisher(config, repo, profile)),
        secret_key=settings.secret_key,
        secure_cookies=settings.secure_cookies,
        allowed_hosts=settings.allowed_hosts,
        brand_label=profile.label,
    )
    logger.info(f"{profile.label} 시작: http://{settings.host}:{settings.port}")
    app.run(host=settings.host, port=settings.port, debug=False, threaded=True, use_reloader=False)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="블로그 관리자 대시보드")
    parser.add_argument(
        "command", nargs="?", default="serve", choices=["serve", "hash-password", "gen-secret"],
    )
    parser.add_argument(
        "--platform", default="tistory", choices=["tistory", "naver"],
        help="발행할 블로그 (기본 tistory). naver는 naver_calendar 탭·하루 1건",
    )
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    if args.command == "hash-password":
        return _hash_password()
    if args.command == "gen-secret":
        print(f"DASHBOARD_SECRET_KEY={secrets.token_urlsafe(48)}")
        return 0
    os.chdir(PROJECT_ROOT)  # credentials.json 등 상대경로 설정 해석 (run_pipeline_b.sh와 동일)
    setup_logging(str(LOG_FILE))
    return _serve(args.platform)


if __name__ == "__main__":
    sys.exit(main())
