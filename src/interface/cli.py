"""
Composition Root — 유일하게 모든 구체 클래스를 아는 진입점.
의존성 역전(DIP): Application/Domain은 Port만 알고, 여기서 구체 구현을 조립.
"""
import logging

from dotenv import load_dotenv

from src.application.use_cases.publish_posts import PublishPostsUseCase
from src.application.use_cases.reset_stuck_posts import ResetStuckPostsUseCase
from src.domain.value_objects.credentials import Credentials
from src.infrastructure.browser.selenium_adapter import SeleniumBrowserAdapter
from src.infrastructure.config import Config
from src.infrastructure.logging_setup import setup_logging
from src.infrastructure.persistence.google_sheets_repo import GoogleSheetsPostRepository

logger = logging.getLogger(__name__)


def main() -> None:
    # 환경 변수 로드
    load_dotenv()
    setup_logging()

    # 설정 검증 (Fail-fast)
    config = Config.from_env()
    config.validate()

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

    # Step 1: 고스트 복구
    reset_count = ResetStuckPostsUseCase(repo=repo).execute()
    if reset_count > 0:
        logger.warning(f"고스트 복구 완료: {reset_count}건")

    # Step 2: 발행
    stats = PublishPostsUseCase(
        repo=repo,
        browser=browser,
        max_posts=config.max_posts,
    ).execute()

    logger.info(
        f"실행 완료 — 발행: {stats.published}, "
        f"실패: {stats.failed}, 건너뜀: {stats.skipped}"
    )


if __name__ == "__main__":
    main()
