"""통합 대시보드(hub) — 마운트, 세션 공유, 로그인 제한 합산."""
from __future__ import annotations

import re

import pytest
from werkzeug.security import generate_password_hash
from werkzeug.test import Client

from src.application.use_cases.list_posts import ListPostsUseCase
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository
from src.interface.web.app import create_app
from src.interface.web.auth import AdminAuthenticator, LoginThrottle
from src.interface.web.hub import build_hub
from src.interface.web.jobs import PublishJobRunner

PASSWORD = "correct horse battery"


def _app(tab: str, throttle: LoginThrottle):
    app = create_app(
        authenticator=AdminAuthenticator("admin", generate_password_hash(PASSWORD)),
        list_posts=ListPostsUseCase(InMemoryPostRepository([])),
        job_runner=PublishJobRunner(publish=lambda row: None),
        secret_key="test-secret-key-0123456789",
        throttle=throttle,
        brand_label=f"{tab} 관리자",
        hub_tab=tab,
    )
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client() -> Client:
    throttle = LoginThrottle(max_attempts=3, window_seconds=600)
    apps = {
        "naver": _app("naver", throttle),
        "tistory": _app("tistory", throttle),
    }
    return Client(build_hub(apps))


def _csrf(client: Client, path: str) -> str:
    html = client.get(path).get_data(as_text=True)
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, f"CSRF 토큰 없음: {path}"
    return match.group(1)


def _login(client: Client, prefix: str, password: str = PASSWORD):
    return client.post(f"{prefix}/login", data={
        "username": "admin", "password": password, "csrf_token": _csrf(client, f"{prefix}/login"),
    })


def test_루트는_네이버로(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/naver/")


def test_로그인_전에는_각_앱의_로그인으로(client):
    resp = client.get("/tistory/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/tistory/login")


def test_한_번_로그인으로_두_탭(client):
    assert _login(client, "/naver").status_code == 302
    assert client.get("/naver/").status_code == 200
    assert client.get("/tistory/").status_code == 200


def test_로그아웃도_함께(client):
    _login(client, "/naver")
    client.post("/tistory/logout", data={"csrf_token": _csrf(client, "/tistory/")})
    assert client.get("/naver/").status_code == 302


def test_로그인_실패_제한은_합산(client):
    _login(client, "/naver", password="nope")
    _login(client, "/naver", password="nope")
    _login(client, "/tistory", password="nope")
    assert _login(client, "/tistory").status_code == 429


def test_링크와_폼에_접두어(client):
    _login(client, "/tistory")
    html = client.get("/tistory/").get_data(as_text=True)
    assert 'action="/tistory/logout"' in html
    assert 'href="/tistory/static/dashboard.css' in html
    assert '<a href="/tistory/" aria-current="page">티스토리</a>' in html


def test_탭_키가_다르면_거부():
    with pytest.raises(ValueError):
        build_hub({"naver": _app("naver", LoginThrottle())})
