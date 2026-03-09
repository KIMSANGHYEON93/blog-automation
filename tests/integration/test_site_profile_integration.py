"""Integration tests for site_profile features — uses REAL services.

테스트 A: site_profile.json 로드 → tistory_editor 주입 → resolve 동작
테스트 B: --sync-categories (Selenium + Tistory 실제 카테고리 fetch)
테스트 C: save_category() via Google Sheets

Run with:
  pytest tests/integration/test_site_profile_integration.py -m integration -v

Requires:
  - .env 파일 (KAKAO_ID, KAKAO_PW, TISTORY_BLOG)
  - credentials.json (Google Sheets 테스트용)
  - site_profile.json (프로젝트 루트)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------

CREDS_PATH = os.getenv("GOOGLE_CREDS", "credentials.json")
SHEET_NAME = os.getenv("SHEET_NAME", "keyword_calendar_v2")
PROFILE_PATH = PROJECT_ROOT / os.getenv("SITE_PROFILE", "site_profile.json")
BROWSER_DATA_DIR = str(PROJECT_ROOT / ".browser_data")


def _has_kakao() -> bool:
    return bool(os.getenv("KAKAO_ID")) and bool(os.getenv("KAKAO_PW"))


def _has_sheets() -> bool:
    return os.path.exists(CREDS_PATH)


def _has_profile() -> bool:
    return PROFILE_PATH.exists()


skip_no_kakao = pytest.mark.skipif(
    not _has_kakao(), reason="KAKAO_ID/KAKAO_PW 미설정",
)
skip_no_sheets = pytest.mark.skipif(
    not _has_sheets(), reason=f"credentials.json 미존재: {CREDS_PATH}",
)
skip_no_profile = pytest.mark.skipif(
    not _has_profile(), reason=f"site_profile.json 미존재: {PROFILE_PATH}",
)


# ===========================================================================
# Test A: site_profile.json 로드 + tistory_editor 주입
# ===========================================================================


@pytest.mark.integration
@skip_no_profile
class TestSiteProfileLoad:
    """site_profile.json 실제 파일 로드 + tistory_editor 연동."""

    def test_load_real_profile(self):
        """실제 site_profile.json 로드 성공."""
        from src.infrastructure.persistence.json_site_profile import JsonSiteProfileAdapter

        adapter = JsonSiteProfileAdapter(PROFILE_PATH)
        profile = adapter.load()

        assert profile.blog_niche, "blog_niche 비어있음"
        assert profile.default_category_id, "default_category_id 비어있음"
        assert len(profile.categories) >= 1, "카테고리 1개 이상 필요"

    def test_resolve_category_id_with_real_profile(self):
        """실제 프로필로 resolve_category_id 동작 확인 (VO 직접 호출)."""
        from src.infrastructure.persistence.json_site_profile import JsonSiteProfileAdapter

        profile = JsonSiteProfileAdapter(PROFILE_PATH).load()

        # 프로필의 첫 번째 카테고리로 resolve 테스트
        first_cat = profile.categories[0]
        result = profile.resolve_category_id(first_cat.name)
        assert result == first_cat.tistory_id, (
            f"'{first_cat.name}' → {result}, 기대: {first_cat.tistory_id}"
        )

        # 빈 값 → default
        assert profile.resolve_category_id("") == profile.default_category_id

    def test_classify_keyword_with_real_profile(self):
        """실제 프로필의 패턴으로 키워드 분류."""
        from src.infrastructure.persistence.json_site_profile import JsonSiteProfileAdapter

        profile = JsonSiteProfileAdapter(PROFILE_PATH).load()

        # 패턴이 있는 카테고리 찾기
        cats_with_patterns = [c for c in profile.categories if c.keyword_patterns]
        if not cats_with_patterns:
            pytest.skip("keyword_patterns 있는 카테고리 없음")

        cat = cats_with_patterns[0]
        # 첫 번째 패턴으로 테스트 키워드 생성
        pattern = cat.keyword_patterns[0]
        suffix = pattern.rstrip("$")
        test_kw = f"테스트{suffix}"

        result = profile.classify_keyword(test_kw)
        assert result == cat.name, f"'{test_kw}' → {result}, 기대: {cat.name}"


# ===========================================================================
# Test B: --sync-categories (Tistory 실제 카테고리 fetch)
# ===========================================================================


@pytest.mark.integration
@skip_no_kakao
@skip_no_profile
class TestCategorySyncIntegration:
    """실제 Tistory 카테고리 fetch + site_profile 비교.

    하나의 브라우저 세션(class scope)으로 2FA 1회만 수행.
    """

    @pytest.fixture(scope="class")
    def browser_session(self):
        """클래스 전체에서 공유하는 브라우저 세션."""
        from src.domain.value_objects.credentials import Credentials
        from src.infrastructure.browser.selenium_adapter import SeleniumBrowserAdapter

        credentials = Credentials(
            kakao_id=os.getenv("KAKAO_ID", ""),
            kakao_pw=os.getenv("KAKAO_PW", ""),
            tistory_blog=os.getenv("TISTORY_BLOG", ""),
        )
        browser = SeleniumBrowserAdapter(
            credentials=credentials,
            headless=False,
            user_data_dir=BROWSER_DATA_DIR,
        )
        browser.start()
        login_ok = browser.login()
        assert login_ok, "로그인 실패"
        yield browser
        browser.stop()

    def test_fetch_remote_categories(self, browser_session):
        """Selenium으로 Tistory /manage/category.json 접근 + 파싱."""
        from src.infrastructure.browser.category_sync_adapter import (
            SeleniumCategorySyncAdapter,
        )

        sync_adapter = SeleniumCategorySyncAdapter(
            sb=browser_session._sb,
            blog_name=browser_session._credentials.tistory_blog,
        )
        categories = sync_adapter.fetch_categories()

        assert len(categories) >= 1, "원격 카테고리 1개 이상 필요"
        for cat in categories:
            assert cat.name, "카테고리 이름 비어있음"
            assert cat.category_id, "카테고리 ID 비어있음"
            print(
                f"  원격: {cat.name} (ID={cat.category_id}, "
                f"parent={cat.parent}, count={cat.entry_count})"
            )

    def test_sync_use_case_dry_run(self, browser_session):
        """SyncCategoriesUseCase dry-run (auto_update=False)."""
        from src.application.use_cases.sync_categories import SyncCategoriesUseCase
        from src.infrastructure.browser.category_sync_adapter import (
            SeleniumCategorySyncAdapter,
        )
        from src.infrastructure.persistence.json_site_profile import JsonSiteProfileAdapter

        profile_port = JsonSiteProfileAdapter(PROFILE_PATH)
        sync_port = SeleniumCategorySyncAdapter(
            sb=browser_session._sb,
            blog_name=browser_session._credentials.tistory_blog,
        )
        uc = SyncCategoriesUseCase(
            profile_port=profile_port,
            sync_port=sync_port,
        )
        result = uc.execute(auto_update=False)

        print(f"\n  synced={result.synced}, diffs={len(result.diffs)}")
        for diff in result.diffs:
            print(
                f"  [{diff.diff_type}] {diff.category_name} "
                f"local={diff.local_id} remote={diff.remote_id}"
            )

        # 결과 자체는 에러 없이 반환되어야 함
        assert isinstance(result.synced, bool)
        assert result.updated is False, "dry-run이므로 updated=False"


# ===========================================================================
# Test C: save_category() via Google Sheets
# ===========================================================================


@pytest.mark.integration
@skip_no_sheets
class TestSaveCategoryIntegration:
    """Google Sheets에 카테고리 저장 + 복원."""

    TEST_ROW = 2

    @pytest.fixture(autouse=True)
    def _backup_category(self):
        """테스트 전 row 2 카테고리 백업 → 테스트 후 복원."""
        from src.infrastructure.persistence.column_map import COL
        from src.infrastructure.persistence.google_sheets_repo import (
            GoogleSheetsPostRepository,
        )

        self.repo = GoogleSheetsPostRepository(
            creds_path=CREDS_PATH, sheet_name=SHEET_NAME,
        )
        self.original = self.repo._sheet.cell(self.TEST_ROW, COL["category"]).value
        yield
        # 복원
        self.repo._sheet.update_cell(self.TEST_ROW, COL["category"], self.original or "")

    def test_save_category_updates_sheet(self):
        """save_category()로 시트 B열 업데이트 확인."""
        from src.infrastructure.persistence.column_map import COL

        self.repo.save_category(self.TEST_ROW, "통합테스트_카테고리")

        actual = self.repo._sheet.cell(self.TEST_ROW, COL["category"]).value
        assert actual == "통합테스트_카테고리", f"기대: '통합테스트_카테고리', 실제: '{actual}'"
