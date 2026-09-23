"""대시보드 플랫폼 조립 — 네이버는 별도 탭·쿼터 1건·네이버 어댑터."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.services.quota_manager import DEFAULT_DAILY_LIMIT
from src.infrastructure.browser.naver.adapter import NaverBrowserAdapter
from src.infrastructure.browser.selenium_adapter import SeleniumBrowserAdapter
from src.infrastructure.config import Config
from src.interface.web.platform import make_browser, resolve_platform


@pytest.fixture
def config(monkeypatch) -> Config:
    monkeypatch.setenv("NAVER_BLOG_ID", "sangpedia")
    monkeypatch.setenv("NAVER_SHEET_TAB", "naver_calendar")
    monkeypatch.setenv("TISTORY_BLOG", "myblog")
    return Config.from_env()


def test_tistory는_기존과_같다(config):
    profile = resolve_platform("tistory", config)
    assert profile.worksheet == ""
    assert profile.daily_limit == DEFAULT_DAILY_LIMIT


def test_naver는_별도_탭과_쿼터_1건(config):
    profile = resolve_platform("naver", config)
    assert profile.worksheet == "naver_calendar"
    assert profile.daily_limit == 1
    assert "네이버" in profile.label


def test_모르는_플랫폼은_거부(config):
    with pytest.raises(ValueError, match="velog"):
        resolve_platform("velog", config)


def test_naver_브라우저는_공개_발행_네이버_어댑터(config, tmp_path):
    browser = make_browser(resolve_platform("naver", config), config, Path(tmp_path), None, None)
    assert isinstance(browser, NaverBrowserAdapter)
    assert browser._draft_only is False
    assert browser._blog_id == "sangpedia"
    assert browser._profile_dir == str(tmp_path / ".browser_data_naver")


def test_tistory_브라우저는_셀레니움_어댑터(config, tmp_path):
    browser = make_browser(resolve_platform("tistory", config), config, Path(tmp_path), None, None)
    assert isinstance(browser, SeleniumBrowserAdapter)
