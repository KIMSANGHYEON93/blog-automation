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
from src.application.use_cases.edit_post import EditPostUseCase
from src.application.use_cases.generate_keywords_from_terms import (
    GenerateKeywordsFromTermsUseCase,
)
from src.application.use_cases.list_posts import ListPostsUseCase
from src.application.use_cases.publish_selected_post import (
    ManualPublishOutcome,
    ManualPublishResult,
    PublishSelectedPostUseCase,
)
from src.application.use_cases.register_keyword import RegisterKeywordUseCase
from src.domain.services.internal_link_service import InternalLinkService
from src.domain.services.quota_manager import QuotaManager
from src.domain.value_objects.post_status import PostStatus
from src.domain.value_objects.site_profile import SiteProfile
from src.infrastructure.browser.naver.adapter import DRAFT_ONLY_MESSAGE, MAX_IMAGES
from src.infrastructure.browser.naver.preview import build_preview_html
from src.infrastructure.browser.tistory_editor import set_site_profile
from src.infrastructure.config import Config
from src.infrastructure.locking.directory_lock import DirectoryPipelineLock
from src.infrastructure.logging_setup import setup_logging
from src.infrastructure.persistence.google_sheets_repo import GoogleSheetsPostRepository
from src.infrastructure.persistence.json_site_profile import JsonSiteProfileAdapter
from src.infrastructure.persistence.sheets_brain_term_adapter import SheetsBrainTermAdapter
from src.interface.cli import _build_notification as build_notification
from src.interface.web.app import create_app
from src.interface.web.auth import AdminAuthenticator
from src.interface.web.generation import (
    DEFAULT_N8N_CONTAINER,
    NAVER_WORKFLOW_NAME,
    build_generator,
)
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


def _build_drafter(  # type: ignore[no-untyped-def]
    config: Config, repo: GoogleSheetsPostRepository, profile: PlatformProfile,
):
    """임시저장 시험: 실제 에디터에 붙여 임시저장까지만. 시트 상태는 바꾸지 않는다."""

    def draft(row_index: int) -> ManualPublishResult:
        post = next((p for p in repo.find_all() if p.row_index == row_index), None)
        if post is None or post.content is None or not post.content.has_body():
            return ManualPublishResult.rejected(row_index, "본문이 없어 시험할 수 없습니다")
        lock = DirectoryPipelineLock(LOCK_DIR)
        if not lock.acquire():
            return ManualPublishResult.rejected(row_index, "다른 작업(자동 발행 등)이 실행 중")
        browser = make_browser(profile, config, PROJECT_ROOT, None, None, draft_only=True)
        try:
            browser.start()
            if not browser.login():
                return ManualPublishResult.failed(
                    row_index, "네이버 로그인 실패 — scripts/naver_blog.py login 으로 다시 로그인",
                )
            result = browser.publish(post)
        finally:
            browser.stop()
            lock.release()
        if result.error != DRAFT_ONLY_MESSAGE:
            return ManualPublishResult.failed(row_index, f"임시저장 시험 실패: {result.error}")
        uploaded = getattr(browser, "images_uploaded", 0)
        return ManualPublishResult(
            ManualPublishOutcome.DRAFTED, row_index,
            f"임시저장 완료 — 사진 {uploaded}/{MAX_IMAGES}장 업로드 확인. "
            "네이버 글쓰기 > 임시저장에서 확인하세요",
        )

    return draft


class _KeywordDesk:
    """대시보드 키워드 화면: AI-Brain 용어 추천 + 직접 등록. 중복은 두 탭 모두와 본다."""

    def __init__(
        self, suggester: GenerateKeywordsFromTermsUseCase, register: RegisterKeywordUseCase,
    ):
        self._suggester = suggester
        self._register = register

    def suggest(self) -> list[str]:
        result = self._suggester.execute()
        return [s.keyword for s in result.suggestions] if result.success else []

    def register(self, keyword: str) -> int:
        return self._register.register(keyword)


def _build_keyword_desk(
    config: Config, repo: GoogleSheetsPostRepository, profile: PlatformProfile,
) -> _KeywordDesk:
    # 다른 블로그 탭 — 네이버 대시보드면 티스토리(sheet1), 티스토리면 네이버 탭
    other_tab = "" if profile.name == "naver" else config.naver_sheet_tab
    other = GoogleSheetsPostRepository(
        creds_path=config.google_creds, sheet_name=config.sheet_name, worksheet=other_tab,
    )
    terms = SheetsBrainTermAdapter(creds_path=config.google_creds, sheet_name=config.sheet_name)
    return _KeywordDesk(
        GenerateKeywordsFromTermsUseCase(repo=repo, term_port=terms, top_n=15, other_repos=[other]),
        RegisterKeywordUseCase(repo, other_repos=[other]),
    )


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
        job_runner=PublishJobRunner(
            publish=_build_publisher(config, repo, profile),
            draft=_build_drafter(config, repo, profile) if profile.name == "naver" else None,
            generate=(
                build_generator(
                    os.getenv("N8N_CONTAINER", DEFAULT_N8N_CONTAINER), NAVER_WORKFLOW_NAME,
                    lambda: sum(1 for p in repo.find_all() if p.status == PostStatus.PENDING),
                ) if profile.name == "naver" else None
            ),
        ),
        edit_post=EditPostUseCase(repo),
        preview=(
            (lambda post: build_preview_html(post.keyword, post.body_markdown))
            if profile.name == "naver" else None
        ),
        keywords=_build_keyword_desk(config, repo, profile),
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
