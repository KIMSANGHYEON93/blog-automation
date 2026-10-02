"""네이버 설정 — NAVER_BLOG_ID는 로그인 아이디가 아니라 블로그 주소다."""
from __future__ import annotations

import pytest

from src.infrastructure.config import Config


@pytest.fixture
def creds_file(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    path.write_text("{}")
    monkeypatch.setenv("GOOGLE_CREDS", str(path))
    return path


def test_기본값(monkeypatch):
    monkeypatch.delenv("NAVER_BLOG_ID", raising=False)
    monkeypatch.delenv("NAVER_SHEET_TAB", raising=False)
    config = Config.from_env()
    assert config.naver_blog_id == ""
    assert config.naver_sheet_tab == "naver_calendar"


def test_환경변수_반영(monkeypatch):
    monkeypatch.setenv("NAVER_BLOG_ID", "sangpedia")
    monkeypatch.setenv("NAVER_SHEET_TAB", "naver_test")
    config = Config.from_env()
    assert config.naver_blog_id == "sangpedia"
    assert config.naver_sheet_tab == "naver_test"


def test_validate_naver_통과(monkeypatch, creds_file):
    monkeypatch.setenv("NAVER_BLOG_ID", "sangpedia")
    Config.from_env().validate_naver()


def test_validate_naver_블로그_아이디_누락(monkeypatch, creds_file):
    monkeypatch.delenv("NAVER_BLOG_ID", raising=False)
    with pytest.raises(OSError, match="NAVER_BLOG_ID"):
        Config.from_env().validate_naver()


def test_validate_naver_자격증명_파일_없음(monkeypatch, tmp_path):
    monkeypatch.setenv("NAVER_BLOG_ID", "sangpedia")
    monkeypatch.setenv("GOOGLE_CREDS", str(tmp_path / "없음.json"))
    with pytest.raises(OSError, match="GOOGLE_CREDS"):
        Config.from_env().validate_naver()


def test_네이버_로그인_설정(monkeypatch):
    monkeypatch.setenv("NAVER_LOGIN_ID", "id")
    monkeypatch.setenv("NAVER_LOGIN_PW", "pw")
    monkeypatch.setenv("NAVER_TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    config = Config.from_env()
    assert (config.naver_login_id, config.naver_login_pw) == ("id", "pw")
    assert config.naver_telegram_bot_token == "123:abc"
    assert config.telegram_chat_id == "42"


def test_네이버_로그인_설정_기본값(monkeypatch):
    for key in ("NAVER_LOGIN_ID", "NAVER_LOGIN_PW", "NAVER_TELEGRAM_BOT_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    config = Config.from_env()
    assert config.naver_login_id == config.naver_login_pw == config.naver_telegram_bot_token == ""


@pytest.mark.parametrize("blog_id, expected", [
    ("sangpedia", "https://blog.naver.com/sangpedia"),
    ("", ""),
    ("bad/../id", ""),
])
def test_네이버_블로그_주소(monkeypatch, blog_id, expected):
    monkeypatch.setenv("NAVER_BLOG_ID", blog_id)
    assert Config.from_env().naver_blog_url == expected
