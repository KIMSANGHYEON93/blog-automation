"""관리자 대시보드 Composition Root.

    python -m src.interface.web hash-password   # 관리자 비밀번호 해시 생성
    python -m src.interface.web gen-secret      # 세션 시크릿 생성
    python -m src.interface.web                 # 대시보드 실행 (기본 http://127.0.0.1:8787)
    python -m src.interface.web --platform naver  # 네이버 대시보드 (naver_calendar 탭)
    python -m src.interface.web hub             # 통합 대시보드 (/naver/ · /tistory/ 탭)
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
from flask import Flask
from werkzeug.security import generate_password_hash
from werkzeug.serving import run_simple

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
from src.application.use_cases.revise_selected_post import ReviseSelectedPostUseCase
from src.application.use_cases.suggest_volume_keywords import (
    KeywordPillar,
    SuggestVolumeKeywordsUseCase,
)
from src.domain.services.internal_link_service import InternalLinkService
from src.domain.services.quota_manager import QuotaManager
from src.domain.value_objects.post_status import PostStatus
from src.domain.value_objects.site_profile import SiteProfile
from src.infrastructure.browser.naver.adapter import (
    DEFAULT_PHOTO_DIR,
    DRAFT_ONLY_MESSAGE,
    MAX_IMAGES,
)
from src.infrastructure.browser.naver.doc_capture import capture_official_docs
from src.infrastructure.browser.naver.images import save_photo
from src.infrastructure.browser.naver.preview import build_preview_html
from src.infrastructure.browser.tistory_editor import set_site_profile
from src.infrastructure.browser.tistory_render import render_tistory_html
from src.infrastructure.config import Config
from src.infrastructure.locking.directory_lock import DirectoryPipelineLock
from src.infrastructure.logging_setup import setup_logging
from src.infrastructure.persistence.google_sheets_repo import GoogleSheetsPostRepository
from src.infrastructure.persistence.json_site_profile import JsonSiteProfileAdapter
from src.infrastructure.persistence.sheets_brain_term_adapter import SheetsBrainTermAdapter
from src.infrastructure.seo.naver_searchad import NaverSearchAdKeywordAdapter
from src.interface.cli import _build_notification as build_notification
from src.interface.web.app import KeywordIdea, create_app
from src.interface.web.auth import AdminAuthenticator, LoginThrottle
from src.interface.web.generation import (
    DEFAULT_N8N_CONTAINER,
    NAVER_WORKFLOW_NAME,
    TISTORY_WORKFLOW_NAME,
    build_generator,
)
from src.interface.web.hub import build_hub
from src.interface.web.jobs import PublishJobRunner
from src.interface.web.platform import (
    PlatformProfile,
    build_kakao_relogin,
    build_relogin,
    dashboard_url,
    make_browser,
    naver_notifier,
    notify_login_failure,
    resolve_platform,
)
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
        if profile.name == "naver":
            notify_login_failure(result, naver_notifier(config), dashboard_url(os.environ))
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


def _tistory_preview(repo: GoogleSheetsPostRepository, config: Config, row_index: int) -> str:
    """티스토리 탭 미리보기 — 발행과 같은 변환으로 최종 HTML. 관련 글은 발행 때 붙는다."""
    post = next((p for p in repo.find_all() if p.row_index == row_index), None)
    if post is None or post.content is None or not post.content.body_markdown:
        return "<p>본문이 없습니다.</p>"
    return render_tistory_html(post, config.tistory_blog, config.naver_blog_url)


def _generation_snapshot(repo: GoogleSheetsPostRepository) -> tuple[int, set[str]]:
    """'지금 생성' 전후 비교용: 발행대기 수와 중복으로 건너뛴 키워드(시트 1회 읽기)."""
    posts = repo.find_all()
    pending = sum(1 for p in posts if p.status == PostStatus.PENDING)
    # n8n 'Sheets Update (중복스킵)'이 남기는 사유 문구(상태값 '중복스킵'은 보류로 읽힌다)
    skipped = {p.keyword for p in posts if p.error_message.startswith("중복 키워드")}
    return pending, skipped


def _build_reviser(  # type: ignore[no-untyped-def]
    config: Config, repo: GoogleSheetsPostRepository, profile: PlatformProfile,
):
    """수정 발행: 대시보드에서 고친 발행 글을 같은 주소에서 고쳐 쓴다(네이버)."""

    def revise(row_index: int) -> ManualPublishResult:
        use_case = ReviseSelectedPostUseCase(
            repo=repo,
            browser=make_browser(profile, config, PROJECT_ROOT, build_notification(), None),
            lock=DirectoryPipelineLock(LOCK_DIR),
        )
        logger.info(f"[{profile.name}] 수정 발행 시작: row={row_index}")
        result = use_case.execute(row_index)
        if profile.name == "naver":
            notify_login_failure(result, naver_notifier(config), dashboard_url(os.environ))
        logger.info(
            f"[{profile.name}] 수정 발행 결과: row={row_index} "
            f"{result.outcome.value} — {result.message}"
        )
        return result

    return revise


class _KeywordDesk:
    """대시보드 키워드 화면: AI-Brain 용어 추천 + 직접 등록. 중복은 두 탭 모두와 본다."""

    source = "AI-Brain 용어에서"

    def __init__(
        self, suggester: GenerateKeywordsFromTermsUseCase, register: RegisterKeywordUseCase,
    ):
        self._suggester = suggester
        self._register = register

    def suggest(self) -> list[KeywordIdea]:
        result = self._suggester.execute()
        return [KeywordIdea(s.keyword) for s in result.suggestions] if result.success else []

    def register(self, keyword: str) -> int:
        return self._register.register(keyword)


# 네이버 블로그 키워드 축: IT·AI 실무가 본진, 경제는 보조(2026-09-29 성장 계획).
# hints는 검색광고 키워드 도구 시드, anchors는 연관 키워드 중 남길 기준 단어
# (없으면 엉뚱한 게 섞인다)
NAVER_KEYWORD_PILLARS = [
    KeywordPillar(
        "AI 실무",
        hints=("챗GPT사용법", "챗GPT엑셀", "AIPPT", "회의록요약", "AI보고서",
               "클로드사용법", "제미나이사용법", "노션AI", "캔바AI", "AI글쓰기"),
        anchors=("AI", "GPT", "지피티", "클로드", "제미나이", "코파일럿", "뤼튼", "퍼플렉시티"),
    ),
    KeywordPillar(
        "경제",
        hints=("연말정산", "정부지원금", "청년도약계좌", "근로장려금", "소득공제"),
        anchors=("연말정산", "지원금", "도약계좌", "장려금", "세액공제", "소득공제", "환급"),
    ),
]


class _VolumeKeywordDesk:
    """네이버 키워드 화면: 검색광고 키워드 도구의 월간 검색량 기준 추천."""

    source = "네이버 월간 검색량(검색광고 키워드 도구)"

    def __init__(self, suggester: SuggestVolumeKeywordsUseCase, register: RegisterKeywordUseCase):
        self._suggester = suggester
        self._register = register

    def suggest(self) -> list[KeywordIdea]:
        try:
            ideas = self._suggester.execute()
        except Exception as e:  # API 장애로 키워드 화면(직접 등록)까지 막지 않는다
            logger.error(f"검색량 키워드 추천 실패: {type(e).__name__}: {e}")
            return []
        return [KeywordIdea(s.keyword, f"월 {s.monthly_searches:,}회 · {s.pillar}")
                for s in ideas]

    def register(self, keyword: str) -> int:
        return self._register.register(keyword)


def _search_ad_port() -> NaverSearchAdKeywordAdapter | None:
    keys = [os.getenv(k, "").strip()
            for k in ("NAVER_AD_API_KEY", "NAVER_AD_SECRET", "NAVER_AD_CUSTOMER_ID")]
    return NaverSearchAdKeywordAdapter(*keys) if all(keys) else None


def _build_keyword_desk(
    config: Config, repo: GoogleSheetsPostRepository, profile: PlatformProfile,
) -> _KeywordDesk | _VolumeKeywordDesk:
    # 다른 블로그 탭 — 네이버 대시보드면 티스토리(sheet1), 티스토리면 네이버 탭
    other_tab = "" if profile.name == "naver" else config.naver_sheet_tab
    other = GoogleSheetsPostRepository(
        creds_path=config.google_creds, sheet_name=config.sheet_name, worksheet=other_tab,
    )
    volumes = _search_ad_port() if profile.name == "naver" else None
    if volumes is not None:
        return _VolumeKeywordDesk(
            # 새 블로그라 월 5천 회 넘는 큰 키워드는 상위 노출이 어렵다 — 롱테일만(성장 계획)
            SuggestVolumeKeywordsUseCase(volumes, [repo, other], NAVER_KEYWORD_PILLARS,
                                         max_searches=5000),
            RegisterKeywordUseCase(repo, other_repos=[other]),
        )
    terms = SheetsBrainTermAdapter(creds_path=config.google_creds, sheet_name=config.sheet_name)
    return _KeywordDesk(
        GenerateKeywordsFromTermsUseCase(repo=repo, term_port=terms, top_n=15, other_repos=[other]),
        RegisterKeywordUseCase(repo, other_repos=[other]),
    )


def _load_settings() -> DashboardSettings | None:
    try:
        return DashboardSettings.from_env(os.environ)
    except SettingsError as e:
        print(f"대시보드 설정 오류: {e}", file=sys.stderr)
        return None


def _build_app(
    platform: str, settings: DashboardSettings, throttle: LoginThrottle | None = None,
    hub_tab: str | None = None,
) -> Flask:
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
    return create_app(
        authenticator=AdminAuthenticator(settings.admin_user, settings.admin_password_hash),
        list_posts=ListPostsUseCase(repo),
        job_runner=PublishJobRunner(
            publish=_build_publisher(config, repo, profile),
            draft=_build_drafter(config, repo, profile) if profile.name == "naver" else None,
            revise=_build_reviser(config, repo, profile) if profile.name == "naver" else None,
            login=(
                build_relogin(config, PROJECT_ROOT, DirectoryPipelineLock(LOCK_DIR))
                if profile.name == "naver"
                else build_kakao_relogin(
                    config, PROJECT_ROOT, DirectoryPipelineLock(LOCK_DIR),
                    _load_site_profile(config), build_notification(),
                )
            ),
            # 두 블로그 모두 — 글 상세의 '본문 생성'은 비고 표시로 그 글 하나만 생성한다
            generate=build_generator(
                os.getenv("N8N_CONTAINER", DEFAULT_N8N_CONTAINER),
                NAVER_WORKFLOW_NAME if profile.name == "naver" else TISTORY_WORKFLOW_NAME,
                lambda: _generation_snapshot(repo),
                mark=repo.set_note,
            ),
        ),
        edit_post=EditPostUseCase(repo),
        preview=(
            (lambda post: build_preview_html(post.keyword, post.body_markdown))
            if profile.name == "naver"
            else (lambda post: _tistory_preview(repo, config, post.row_index))
        ),
        preview_raw=profile.name != "naver",
        keywords=_build_keyword_desk(config, repo, profile),
        daily_limit=profile.daily_limit,
        secret_key=settings.secret_key,
        throttle=throttle,
        secure_cookies=settings.secure_cookies,
        allowed_hosts=settings.allowed_hosts,
        brand_label=profile.label,
        relogin_label=profile.relogin_label,
        approve_hint=profile.approve_hint,
        hub_tab=hub_tab,
        # 사진 첨부는 네이버만 — 경험 문단 규칙이 네이버에만 있다
        photo_store=(
            (lambda data: save_photo(data, PROJECT_ROOT / DEFAULT_PHOTO_DIR))
            if profile.name == "naver" else None
        ),
        # 공식 문서 캡처는 두 블로그 모두 — 티스토리는 발행 때 첨부로 올려 치환자로 바꾼다
        doc_capture=lambda urls: capture_official_docs(urls, PROJECT_ROOT / DEFAULT_PHOTO_DIR),
    )


def _serve(platform: str) -> int:
    settings = _load_settings()
    if settings is None:
        return 2
    app = _build_app(platform, settings)
    logger.info(f"대시보드 시작: http://{settings.host}:{settings.port}")
    app.run(host=settings.host, port=settings.port, debug=False, threaded=True, use_reloader=False)
    return 0


def _serve_hub() -> int:
    settings = _load_settings()
    if settings is None:
        return 2
    throttle = LoginThrottle()  # 두 앱 합산 — 따로 두면 실패 허용 횟수가 두 배가 된다
    hub = build_hub({
        name: _build_app(name, settings, throttle, hub_tab=name) for name in ("naver", "tistory")
    })
    logger.info(f"통합 대시보드 시작: http://{settings.host}:{settings.port}/")
    run_simple(settings.host, settings.port, hub, threaded=True, use_reloader=False)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="블로그 관리자 대시보드")
    parser.add_argument(
        "command", nargs="?", default="serve",
        choices=["serve", "hub", "hash-password", "gen-secret"],
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
    if args.command == "hub":
        return _serve_hub()
    return _serve(args.platform)


if __name__ == "__main__":
    sys.exit(main())
