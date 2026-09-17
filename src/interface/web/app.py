"""관리자 대시보드 Flask 앱 — 로그인한 관리자만 게시물 현황 조회/수동 발행.

보안: 세션 로그인(HttpOnly, SameSite=Strict), 모든 POST CSRF 검증, IP별 로그인 시도 제한,
CSP/X-Frame-Options/no-store 헤더, Jinja 자동 이스케이프.
"""
from __future__ import annotations

import hmac
import secrets
from datetime import timedelta
from typing import Protocol
from urllib.parse import urlsplit

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from src.application.use_cases.list_posts import PostPage, PostQuery, PostSummary
from src.domain.value_objects.post_status import PostStatus
from src.interface.web.auth import AdminAuthenticator, LoginThrottle
from src.interface.web.jobs import JobState, PublishJobRunner

PUBLIC_ENDPOINTS = frozenset({"login", "static", "favicon"})
SAFE_URL_SCHEMES = frozenset({"http", "https"})
JOB_REFRESH_SECONDS = 3
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'none'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class PostReader(Protocol):
    def execute(self, query: PostQuery) -> PostPage: ...

    def get(self, row_index: int) -> PostSummary | None: ...


def create_app(
    *,
    authenticator: AdminAuthenticator,
    list_posts: PostReader,
    job_runner: PublishJobRunner,
    secret_key: str,
    throttle: LoginThrottle | None = None,
    secure_cookies: bool = False,
    session_hours: int = 8,
    allowed_hosts: frozenset[str] | None = None,
) -> Flask:
    if len(secret_key) < 16:
        raise ValueError("secret_key는 16자 이상이어야 합니다")
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=secure_cookies,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=session_hours),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    login_throttle = throttle or LoginThrottle()
    _register_guards(app, allowed_hosts)
    _register_auth_routes(app, authenticator, login_throttle)
    _register_dashboard_routes(app, list_posts, job_runner)
    return app


def _csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return str(session["csrf_token"])


def safe_url(value: str) -> str:
    """http/https 절대 URL만 링크로 허용 (시트 데이터의 javascript: 등 차단)."""
    parts = urlsplit((value or "").strip())
    return parts.geturl() if parts.scheme.lower() in SAFE_URL_SCHEMES and parts.netloc else ""


def _register_guards(app: Flask, allowed_hosts: frozenset[str] | None) -> None:
    app.jinja_env.globals["csrf_token"] = _csrf_token
    app.jinja_env.filters["safe_url"] = safe_url

    @app.get("/favicon.ico")
    def favicon():  # type: ignore[no-untyped-def]
        return "", 204

    @app.before_request
    def require_admin_and_csrf():  # type: ignore[no-untyped-def]
        # DNS rebinding 방지: 로컬 바인딩에서는 예상한 Host만 허용
        if allowed_hosts is not None and request.host not in allowed_hosts:
            abort(400, description="허용되지 않은 Host")
        if request.method == "POST":
            sent = request.form.get("csrf_token", "")
            expected = session.get("csrf_token", "")
            if not sent or not expected or not hmac.compare_digest(sent, expected):
                abort(400, description="CSRF 토큰이 유효하지 않습니다")
        if request.endpoint not in PUBLIC_ENDPOINTS and not session.get("admin"):
            return redirect(url_for("login"))
        return None

    @app.after_request
    def security_headers(response):  # type: ignore[no-untyped-def]
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response


def _register_auth_routes(
    app: Flask, authenticator: AdminAuthenticator, throttle: LoginThrottle,
) -> None:
    @app.route("/login", methods=["GET", "POST"])
    def login():  # type: ignore[no-untyped-def]
        if request.method == "GET":
            return render_template("login.html")
        client = request.remote_addr or "unknown"
        if throttle.is_blocked(client):
            return render_template(
                "login.html", error="로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.",
            ), 429
        username = request.form.get("username", "")
        if not authenticator.verify(username, request.form.get("password", "")):
            throttle.record_failure(client)
            return render_template(
                "login.html", error="사용자명 또는 비밀번호가 올바르지 않습니다.",
            ), 401
        throttle.reset(client)
        session.clear()  # 세션 고정 공격 방지: 로그인 시 새 세션
        session["admin"] = username
        session.permanent = True
        _csrf_token()
        return redirect(url_for("index"))

    @app.post("/logout")
    def logout():  # type: ignore[no-untyped-def]
        session.clear()
        return redirect(url_for("login"))


def _parse_status(raw: str) -> PostStatus | None:
    try:
        return PostStatus.from_string(raw) if raw else None
    except ValueError:
        return None


def _register_dashboard_routes(app: Flask, reader: PostReader, runner: PublishJobRunner) -> None:
    @app.get("/")
    def index():  # type: ignore[no-untyped-def]
        status = _parse_status(request.args.get("status", ""))
        search = request.args.get("q", "")[:100]
        page = reader.execute(PostQuery(status=status, search=search))
        return render_template(
            "dashboard.html", page=page, statuses=list(PostStatus),
            selected_status=status, search=search,
            active_job=runner.active_job(), recent_jobs=runner.recent()[:5],
        )

    @app.get("/posts/<int:row_index>")
    def post_detail(row_index: int):  # type: ignore[no-untyped-def]
        post = reader.get(row_index)
        if post is None:
            abort(404)
        return render_template("post_detail.html", post=post, active_job=runner.active_job())

    @app.post("/posts/<int:row_index>/publish")
    def publish(row_index: int):  # type: ignore[no-untyped-def]
        job_id = runner.submit(row_index)
        if job_id is None:
            flash("이미 진행 중인 발행 작업이 있습니다. 끝난 뒤 다시 시도하세요.", "error")
            return redirect(url_for("post_detail", row_index=row_index))
        return redirect(url_for("job_status", job_id=job_id))

    @app.get("/jobs/<job_id>")
    def job_status(job_id: str):  # type: ignore[no-untyped-def]
        job = runner.get(job_id)
        if job is None:
            abort(404)
        return render_template(
            "job.html", job=job, running=job.state == JobState.RUNNING,
            refresh_seconds=JOB_REFRESH_SECONDS,
        )
