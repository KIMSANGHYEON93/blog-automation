"""Integration tests for SeleniumBrowserAdapter — uses a REAL browser.

Run with: pytest tests/integration/test_selenium_adapter.py -m integration
Requires: KAKAO_ID, KAKAO_PW, TISTORY_BLOG environment variables set.
"""
from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from src.domain.value_objects.credentials import Credentials
from src.infrastructure.browser.selenium_adapter import SeleniumBrowserAdapter

load_dotenv()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BROWSER_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".browser_data",
)


def _has_kakao_credentials() -> bool:
    return bool(os.getenv("KAKAO_ID")) and bool(os.getenv("KAKAO_PW"))


skip_no_kakao = pytest.mark.skipif(
    not _has_kakao_credentials(),
    reason="KAKAO_ID or KAKAO_PW not set in environment",
)


@pytest.fixture()
def credentials():
    """Build Credentials from environment variables."""
    kakao_id = os.getenv("KAKAO_ID", "")
    kakao_pw = os.getenv("KAKAO_PW", "")
    tistory_blog = os.getenv("TISTORY_BLOG", "")
    if not kakao_id or not kakao_pw:
        pytest.skip("KAKAO_ID or KAKAO_PW not set in environment")
    return Credentials(kakao_id=kakao_id, kakao_pw=kakao_pw, tistory_blog=tistory_blog)


@pytest.fixture()
def adapter(credentials):
    """Create a SeleniumBrowserAdapter with headless=False and cookie persistence."""
    return SeleniumBrowserAdapter(
        credentials=credentials,
        headless=False,
        min_delay=0,
        max_delay=0,
        user_data_dir=BROWSER_DATA_DIR,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@skip_no_kakao
class TestSeleniumAdapterIntegration:
    """Integration tests that require a real browser instance."""

    def test_start_and_stop_browser(self, adapter):
        """Verify the browser starts and stops without error."""
        adapter.start()
        try:
            # The internal SeleniumBase instance should be alive
            assert adapter._sb is not None, "Browser instance should be set after start()"
        finally:
            adapter.stop()

        assert adapter._sb is None, "Browser instance should be None after stop()"
        assert adapter._sb_context is None, "SB context should be None after stop()"

    def test_login_with_cookies(self, adapter):
        """Verify Kakao login succeeds (uses cookie persistence via .browser_data)."""
        adapter.start()
        try:
            success = adapter.login()
            assert success is True, "Kakao login should succeed with valid credentials"
        finally:
            adapter.stop()

    def test_editor_page_loads(self, adapter):
        """Verify Tistory editor page loads after login."""
        adapter.start()
        try:
            # Login first
            login_ok = adapter.login()
            assert login_ok, "Login must succeed before testing editor page"

            # Navigate to the editor
            tistory_blog = adapter._credentials.tistory_blog
            if not tistory_blog:
                pytest.skip("TISTORY_BLOG not set — cannot test editor page")

            editor_url = f"https://{tistory_blog}.tistory.com/manage/newpost"
            adapter._sb.open(editor_url)

            import time
            time.sleep(3)

            current_url = adapter._sb.get_current_url()
            assert "tistory.com" in current_url, (
                f"Expected tistory.com in URL, got {current_url}"
            )
            # Verify we are on the editor or manage page (not redirected to login)
            assert "/auth/login" not in current_url, (
                f"Should not be on login page, got {current_url}"
            )
        finally:
            adapter.stop()
