"""대시보드 플랫폼 조립 — 네이버는 별도 탭·쿼터 1건·네이버 어댑터."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.application.use_cases.publish_selected_post import (
    LOGIN_FAILED,
    ManualPublishOutcome,
    ManualPublishResult,
)
from src.domain.services.quota_manager import DEFAULT_DAILY_LIMIT
from src.infrastructure.browser.naver.adapter import NaverBrowserAdapter
from src.infrastructure.browser.selenium_adapter import SeleniumBrowserAdapter
from src.infrastructure.config import Config
from src.infrastructure.notification.null_adapter import NullNotificationAdapter
from src.infrastructure.notification.telegram_adapter import TelegramNotificationAdapter
from src.interface.web.platform import (
    build_kakao_relogin,
    build_relogin,
    dashboard_url,
    make_browser,
    naver_notifier,
    notify_if_expired,
    notify_login_failure,
    resolve_platform,
    session_expired_message,
)


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
    assert profile.relogin_label == "네이버 다시 로그인"


def test_포탈_이름은_두_블로그가_같다(config):
    assert resolve_platform("naver", config).label == "통합 블로그 포탈"
    tistory = resolve_platform("tistory", config)
    assert tistory.label == "통합 블로그 포탈"
    assert tistory.relogin_label == "카카오톡 다시 로그인"


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


class _Notifier:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, message, level="INFO"):
        self.sent.append((message, level))
        return True


class _Lock:
    def __init__(self, free=True):
        self.free, self.released = free, False

    def acquire(self):
        return self.free

    def release(self):
        self.released = True


def test_새_봇은_토큰과_채팅이_모두_있을_때만(monkeypatch):
    monkeypatch.setenv("NAVER_TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    assert isinstance(naver_notifier(Config.from_env()), TelegramNotificationAdapter)
    monkeypatch.delenv("NAVER_TELEGRAM_BOT_TOKEN")
    assert isinstance(naver_notifier(Config.from_env()), NullNotificationAdapter)


def test_대시보드_주소():
    assert dashboard_url({"DASHBOARD_EXTRA_HOSTS": "mac.tail.ts.net, other"}) == \
        "https://mac.tail.ts.net/"
    assert dashboard_url({}) == ""


def test_만료_알림_문구():
    assert "네이버 다시 로그인" in session_expired_message("")
    assert session_expired_message("https://mac.ts.net/").endswith("https://mac.ts.net/")


def test_세션이_살아_있으면_알리지_않는다():
    n = _Notifier()
    assert notify_if_expired(True, n, "u") is False and n.sent == []
    assert notify_if_expired(False, n, "https://m/") is True
    assert n.sent[0][1] == "WARNING" and "https://m/" in n.sent[0][0]


def test_로그인_실패_결과만_알린다():
    n = _Notifier()
    notify_login_failure(ManualPublishResult.failed(2, "본문 없음"), n, "")
    assert n.sent == []
    notify_login_failure(ManualPublishResult.failed(2, f"{LOGIN_FAILED} — 발행대기 유지"), n, "")
    assert len(n.sent) == 1


def test_재로그인_작업_성공(config, tmp_path, monkeypatch):
    monkeypatch.setattr(
        NaverBrowserAdapter, "relogin", lambda self, i, p: (True, "네이버 로그인 성공"),
    )
    lock = _Lock()
    result = build_relogin(config, tmp_path, lock)(0)
    assert result.outcome is ManualPublishOutcome.LOGGED_IN
    assert lock.released


def test_재로그인_작업_실패는_실패_결과(config, tmp_path, monkeypatch):
    monkeypatch.setattr(
        NaverBrowserAdapter, "relogin", lambda self, i, p: (False, "폰 승인 시간 초과"),
    )
    result = build_relogin(config, tmp_path, _Lock())(0)
    assert result.outcome is ManualPublishOutcome.FAILED
    assert "시간 초과" in result.message


def test_재로그인은_락이_잡혀_있으면_거부(config, tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        NaverBrowserAdapter, "relogin", lambda self, i, p: called.append(1) or (True, ""),
    )
    result = build_relogin(config, tmp_path, _Lock(free=False))(0)
    assert result.outcome is ManualPublishOutcome.REJECTED and called == []


class _KakaoBrowser:
    def __init__(self, ok=True, error=None):
        self.ok, self.error, self.stopped = ok, error, False

    def start(self):
        pass

    def login(self):
        if self.error:
            raise self.error
        return self.ok

    def stop(self):
        self.stopped = True


def _kakao(config, tmp_path, monkeypatch, browser, lock):
    monkeypatch.setattr(
        "src.interface.web.platform.make_browser", lambda *args, **kwargs: browser,
    )
    return build_kakao_relogin(config, tmp_path, lock, None, None)(0)


def test_카카오_재로그인_성공(config, tmp_path, monkeypatch):
    browser, lock = _KakaoBrowser(), _Lock()
    result = _kakao(config, tmp_path, monkeypatch, browser, lock)
    assert result.outcome is ManualPublishOutcome.LOGGED_IN
    assert browser.stopped and lock.released


def test_카카오_재로그인_실패는_브라우저를_닫고_락을_푼다(config, tmp_path, monkeypatch):
    browser, lock = _KakaoBrowser(ok=False), _Lock()
    result = _kakao(config, tmp_path, monkeypatch, browser, lock)
    assert result.outcome is ManualPublishOutcome.FAILED
    assert "승인" in result.message and browser.stopped and lock.released


def test_카카오_재로그인_중_예외도_결과로_돌려주고_락을_푼다(config, tmp_path, monkeypatch):
    browser, lock = _KakaoBrowser(error=RuntimeError("chrome 실패")), _Lock()
    result = _kakao(config, tmp_path, monkeypatch, browser, lock)
    assert result.outcome is ManualPublishOutcome.FAILED
    assert "RuntimeError" in result.message and browser.stopped and lock.released


def test_카카오_재로그인은_락이_잡혀_있으면_브라우저를_열지_않는다(config, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("브라우저를 열면 안 된다")

    monkeypatch.setattr("src.interface.web.platform.make_browser", forbidden)
    result = build_kakao_relogin(config, tmp_path, _Lock(free=False), None, None)(0)
    assert result.outcome is ManualPublishOutcome.REJECTED
