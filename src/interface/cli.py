"""
Composition Root — 유일하게 모든 구체 클래스를 아는 진입점.
의존성 역전(DIP): Application/Domain은 Port만 알고, 여기서 구체 구현을 조립.
"""
import argparse
import logging
import os

from dotenv import load_dotenv

from src.application.use_cases.check_cwv import CheckCwvUseCase
from src.application.use_cases.check_indexing import CheckIndexingUseCase
from src.application.use_cases.discover_keywords import DiscoverKeywordsUseCase
from src.application.use_cases.generate_sitemap import GenerateSitemapUseCase
from src.application.use_cases.get_status import GetStatusUseCase
from src.application.use_cases.publish_posts import PublishPostsUseCase
from src.application.use_cases.reset_stuck_posts import ResetStuckPostsUseCase
from src.application.use_cases.revise_posts import RevisePostsUseCase
from src.application.use_cases.submit_indexing import SubmitIndexingUseCase
from src.domain.value_objects.credentials import Credentials
from src.infrastructure.browser.selenium_adapter import SeleniumBrowserAdapter
from src.infrastructure.config import Config
from src.infrastructure.logging_setup import setup_logging
from src.infrastructure.persistence.google_sheets_repo import GoogleSheetsPostRepository

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tistory 블로그 자동 발행 시스템",
    )
    parser.add_argument(
        "--publish-pages",
        action="store_true",
        help="AdSense 필수 페이지(소개, 개인정보처리방침, 문의) 발행",
    )
    parser.add_argument(
        "--revise",
        action="store_true",
        help="수정대기 포스트를 기존 Tistory 글에 업데이트",
    )
    parser.add_argument(
        "--check-index",
        action="store_true",
        help="발행완료 포스트의 Google 색인 상태 점검 (미색인 → 수정대기)",
    )
    parser.add_argument(
        "--submit-index",
        action="store_true",
        help="발행완료 포스트를 Google Indexing API에 색인 제출",
    )
    parser.add_argument(
        "--generate-sitemap",
        action="store_true",
        help="발행완료 포스트로 sitemap.xml 생성",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="블로그 현황 대시보드 출력",
    )
    parser.add_argument(
        "--discover-keywords",
        action="store_true",
        help="GSC 검색 데이터에서 키워드 자동 발굴",
    )
    return parser.parse_args()


def _build_notification():
    """알림 어댑터 조립. 환경변수 미설정 시 NullAdapter."""
    slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat = os.getenv("TELEGRAM_CHAT_ID", "")

    if slack_url:
        from src.infrastructure.notification.slack_adapter import SlackNotificationAdapter
        return SlackNotificationAdapter(webhook_url=slack_url)
    if telegram_token and telegram_chat:
        from src.infrastructure.notification.telegram_adapter import (
            TelegramNotificationAdapter,
        )
        return TelegramNotificationAdapter(
            bot_token=telegram_token, chat_id=telegram_chat,
        )

    from src.infrastructure.notification.null_adapter import NullNotificationAdapter
    return NullNotificationAdapter()


def _publish_pages(config: Config) -> None:
    """AdSense 필수 페이지 발행 워크플로우."""
    from src.infrastructure.browser.adsense_pages import publish_pages

    config.validate_pages()

    credentials = Credentials(
        kakao_id=config.kakao_id,
        kakao_pw=config.kakao_pw,
        tistory_blog=config.tistory_blog,
    )
    browser = SeleniumBrowserAdapter(
        credentials=credentials,
        headless=config.headless,
        user_data_dir=".browser_data",
    )

    browser.start()
    try:
        if not browser.login():
            logger.error("로그인 실패 — 페이지 발행 중단")
            return

        results = publish_pages(
            browser._sb,
            blog_name=config.tistory_blog,
            contact_email=config.contact_email,
            owner_name=config.owner_name,
        )

        published = sum(1 for r in results if r.success and r.url)
        skipped = sum(1 for r in results if r.success and not r.url)
        failed = sum(1 for r in results if not r.success)
        logger.info(
            f"AdSense 페이지 발행 완료 — "
            f"발행: {published}, 건너뜀: {skipped}, 실패: {failed}"
        )
    finally:
        browser.stop()


def _revise(config: Config) -> None:
    """수정대기 포스트를 기존 Tistory 글에 업데이트하는 워크플로우."""
    config.validate()

    repo = GoogleSheetsPostRepository(
        creds_path=config.google_creds,
        sheet_name=config.sheet_name,
    )
    credentials = Credentials(
        kakao_id=config.kakao_id,
        kakao_pw=config.kakao_pw,
        tistory_blog=config.tistory_blog,
    )
    browser = SeleniumBrowserAdapter(
        credentials=credentials,
        headless=config.headless,
        min_delay=config.min_delay,
        max_delay=config.max_delay,
        user_data_dir=".browser_data",
    )

    # Step 1: 고스트 복구 (PUBLISHING + REVISING 모두 복구)
    reset_count = ResetStuckPostsUseCase(repo=repo).execute()
    if reset_count > 0:
        logger.warning(f"고스트 복구 완료: {reset_count}건")

    # Step 2: 수정
    stats = RevisePostsUseCase(
        repo=repo,
        browser=browser,
        max_posts=config.max_posts,
    ).execute()

    logger.info(
        f"수정 완료 — 수정: {stats.revised}, "
        f"실패: {stats.failed}, 건너뜀: {stats.skipped}"
    )


def _check_index(config: Config) -> None:
    """발행완료 포스트의 Google 색인 상태 점검 워크플로우."""
    import time as _time

    config.validate()

    repo = GoogleSheetsPostRepository(
        creds_path=config.google_creds,
        sheet_name=config.sheet_name,
    )

    from src.infrastructure.seo.indexing_checker import GscIndexingAdapter

    indexing = GscIndexingAdapter()
    uc = CheckIndexingUseCase(repo=repo, indexing=indexing)
    published = repo.find_published(limit=50)
    if not published:
        logger.info("색인 점검 대상 포스트 없음")
        return

    checked = 0
    indexed = 0
    marked = 0
    for idx, post in enumerate(published):
        if idx > 0:
            _time.sleep(1)  # API rate limit 회피
        result = uc.execute(post)
        if result.success:
            checked += 1
            if result.is_indexed:
                indexed += 1
            if result.marked_revision:
                marked += 1
            logger.info(
                f"색인 점검: {result.post_keyword} — "
                f"indexed={result.is_indexed}, "
                f"verdict={result.verdict}"
            )
        elif result.error:
            logger.warning(
                f"색인 점검 실패: {result.post_keyword} — {result.error}"
            )
            if "quota" in result.error.lower() or "429" in result.error:
                logger.warning("GSC API rate limit — 색인 점검 중단")
                break

    logger.info(
        f"색인 점검 완료: {checked}/{len(published)}건 점검, "
        f"색인됨: {indexed}, 미색인→수정대기: {marked}"
    )


def _submit_index(config: Config) -> None:
    """발행완료 포스트를 Google Indexing API에 색인 제출."""
    config.validate()

    repo = GoogleSheetsPostRepository(
        creds_path=config.google_creds,
        sheet_name=config.sheet_name,
    )

    from src.infrastructure.seo.indexing_submitter import GscIndexingSubmitAdapter

    submitter = GscIndexingSubmitAdapter()
    uc = SubmitIndexingUseCase(repo=repo, indexing_submit=submitter)

    stats = uc.execute()

    notifier = _build_notification()
    msg = (
        f"색인 제출 완료: 제출={stats.submitted}, "
        f"실패={stats.failed}, 건너뜀={stats.skipped}"
    )
    logger.info(msg)
    notifier.send(msg)


def _generate_sitemap(config: Config) -> None:
    """발행완료 포스트로 sitemap.xml 생성."""
    config.validate()

    repo = GoogleSheetsPostRepository(
        creds_path=config.google_creds,
        sheet_name=config.sheet_name,
    )

    from src.infrastructure.seo.sitemap_generator import XmlSitemapAdapter

    sitemap = XmlSitemapAdapter()
    uc = GenerateSitemapUseCase(repo=repo, sitemap=sitemap)

    output_path = config.sitemap_output
    result = uc.execute(output_path)

    if result.success:
        logger.info(f"sitemap.xml 생성: {result.entry_count}개 URL → {result.output_path}")
    else:
        logger.error(f"sitemap 생성 실패: {result.error}")


def _status(config: Config) -> None:
    """블로그 현황 대시보드 출력."""
    config.validate()

    repo = GoogleSheetsPostRepository(
        creds_path=config.google_creds,
        sheet_name=config.sheet_name,
    )
    uc = GetStatusUseCase(repo)
    report = uc.execute()
    print(uc.format_report(report))


def _discover_keywords(config: Config) -> None:
    """GSC 검색 데이터에서 키워드 발굴."""
    config.validate()

    repo = GoogleSheetsPostRepository(
        creds_path=config.google_creds,
        sheet_name=config.sheet_name,
    )

    from src.infrastructure.seo.keyword_researcher import GscKeywordResearchAdapter

    kr = GscKeywordResearchAdapter()
    uc = DiscoverKeywordsUseCase(repo=repo, keyword_research=kr)

    site_url = f"https://{config.tistory_blog}.tistory.com/"
    result = uc.execute(site_url)

    if result.success:
        logger.info(
            f"키워드 발굴: 전체 {result.total_queries}건 → "
            f"필터링 {result.filtered}건 → 제안 {len(result.suggestions)}건"
        )
        for i, s in enumerate(result.suggestions, 1):
            print(
                f"  {i}. {s.keyword} "
                f"(노출={s.impressions}, CTR={s.ctr:.1%}, "
                f"순위={s.position:.1f}, 기회={s.opportunity_score:.0f})"
            )
    else:
        logger.error(f"키워드 발굴 실패: {result.error}")


def main() -> None:
    # 환경 변수 로드
    load_dotenv()
    setup_logging()

    args = _parse_args()
    config = Config.from_env()

    if args.publish_pages:
        _publish_pages(config)
        return

    if args.revise:
        _revise(config)
        return

    if args.check_index:
        _check_index(config)
        return

    if args.submit_index:
        _submit_index(config)
        return

    if args.generate_sitemap:
        _generate_sitemap(config)
        return

    if args.status:
        _status(config)
        return

    if args.discover_keywords:
        _discover_keywords(config)
        return

    # --- 기존 파이프라인 (변경 없음) ---
    config.validate()
    notifier = _build_notification()

    # 의존성 조립 (Composition Root)
    repo = GoogleSheetsPostRepository(
        creds_path=config.google_creds,
        sheet_name=config.sheet_name,
    )
    credentials = Credentials(
        kakao_id=config.kakao_id,
        kakao_pw=config.kakao_pw,
        tistory_blog=config.tistory_blog,
    )
    browser = SeleniumBrowserAdapter(
        credentials=credentials,
        headless=config.headless,
        min_delay=config.min_delay,
        max_delay=config.max_delay,
        user_data_dir=".browser_data",
    )

    # Step 1: 고스트 복구 (+ 옵트인 실패 재시도)
    retry_failed = os.getenv("RETRY_FAILED", "false").lower() == "true"
    reset_count = ResetStuckPostsUseCase(repo=repo, retry_failed=retry_failed).execute()
    if reset_count > 0:
        logger.warning(f"고스트 복구 완료: {reset_count}건")

    # Step 2: 발행
    stats = PublishPostsUseCase(
        repo=repo,
        browser=browser,
        max_posts=config.max_posts,
    ).execute()

    msg = (
        f"실행 완료 — 발행: {stats.published}, "
        f"실패: {stats.failed}, 건너뜀: {stats.skipped}"
    )
    logger.info(msg)

    # 발행 결과 알림
    if stats.published > 0 or stats.failed > 0:
        level = "ERROR" if stats.failed > 0 else "INFO"
        notifier.send(msg, level=level)

    # Step 3: CWV 점검 (발행완료 포스트 대상)
    cwv_enabled = os.getenv("CWV_CHECK", "true").lower() == "true"
    if cwv_enabled:
        import time as _time

        from src.infrastructure.seo.cwv_checker import PageSpeedCwvAdapter

        cwv = PageSpeedCwvAdapter()
        cwv_uc = CheckCwvUseCase(repo=repo, cwv=cwv)
        unchecked = repo.find_cwv_unchecked(limit=10)
        checked = 0
        for idx, post in enumerate(unchecked):
            if idx > 0:
                _time.sleep(3)  # PageSpeed API rate limit 회피
            result = cwv_uc.execute(post)
            if result.success:
                checked += 1
                logger.info(
                    f"CWV: {result.post_keyword} — "
                    f"LCP={result.lcp}s, CLS={result.cls}, "
                    f"Score={result.score}, Passed={result.passed}"
                )
                # CWV 경고 알림
                if not result.passed:
                    notifier.send(
                        f"CWV 경고: {result.post_keyword} — "
                        f"LCP={result.lcp}s, CLS={result.cls}",
                        level="WARNING",
                    )
            elif result.error:
                logger.warning(f"CWV 실패: {result.post_keyword} — {result.error}")
                if "429" in result.error:
                    logger.warning("PageSpeed API rate limit — CWV 점검 중단")
                    break
        logger.info(f"CWV 점검 완료: {checked}/{len(unchecked)}건")


if __name__ == "__main__":
    main()
