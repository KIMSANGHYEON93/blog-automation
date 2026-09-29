"""관리자 대시보드 Flask 앱 — 로그인한 관리자만 게시물 현황 조회/수동 발행.

보안: 세션 로그인(HttpOnly, SameSite=Strict), 모든 POST CSRF 검증, IP별 로그인 시도 제한,
CSP/X-Frame-Options/no-store 헤더, Jinja 자동 이스케이프.
"""
from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Callable, Protocol
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

from src.application.use_cases.edit_post import EditPostUseCase, PostNotEditableError
from src.application.use_cases.list_posts import PostPage, PostQuery, PostSummary
from src.application.use_cases.register_keyword import DuplicateKeywordError
from src.domain.exceptions import InvalidStatusTransitionError
from src.domain.value_objects.post_status import PostStatus
from src.interface.web.auth import AdminAuthenticator, LoginThrottle
from src.interface.web.jobs import JobState, PublishJobRunner

PUBLIC_ENDPOINTS = frozenset({"login", "static", "favicon"})
SAFE_URL_SCHEMES = frozenset({"http", "https"})
JOB_REFRESH_SECONDS = 3
# .pipeline_b.lock을 잡는 launchd 실행 시각(run_pipeline_b.sh). 그 직전에 수동 발행이 락을 쥐고
# 있으면 자동 실행이 [SKIP]으로 조용히 건너뛰어진다. launchd 시각을 바꾸면 여기도 바꿀 것
AUTOMATION_TIMES = (time(0, 0), time(8, 30), time(9, 0), time(10, 0), time(14, 0), time(14, 30))
AUTOMATION_GUARD = timedelta(minutes=20)  # 네이버 발행(사진 5장) 소요 시간보다 넉넉하게
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


@dataclass(frozen=True)
class KeywordIdea:
    keyword: str
    detail: str = ""  # 예: '월 3,210회 · 경제' — 추천 근거


class KeywordDesk(Protocol):
    """키워드 추천(두 탭과 중복 제외)과 등록. 등록은 중복이면 DuplicateKeywordError."""

    source: str  # 추천 출처 — 화면 제목에 쓴다

    def suggest(self) -> list[KeywordIdea]: ...

    def register(self, keyword: str) -> int: ...


KEYWORD_MAX_LENGTH = 60
JOB_LABELS = {"publish": "수동 발행", "draft": "임시저장 시험", "generate": "글 생성",
              "revise": "수정 발행"}


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
    brand_label: str = "블로그 관리자",
    edit_post: EditPostUseCase | None = None,
    preview: Callable[[PostSummary], str] | None = None,
    keywords: KeywordDesk | None = None,
    daily_limit: int | None = None,
    clock: Callable[[], datetime] = datetime.now,
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
        # 본문 편집 폼: 한글은 URL 인코딩 시 글자당 9바이트 — 3만 자 본문도 들어가게
        MAX_CONTENT_LENGTH=512 * 1024,
    )
    login_throttle = throttle or LoginThrottle()
    _register_guards(app, allowed_hosts, brand_label)
    app.jinja_env.globals["daily_limit"] = daily_limit  # 목록 상단 발행 현황(없으면 숨김)
    _register_auth_routes(app, authenticator, login_throttle)
    _register_dashboard_routes(app, list_posts, job_runner, clock)
    if edit_post is not None:
        _register_edit_routes(app, edit_post)
    _register_check_routes(app, list_posts, job_runner, preview, clock)
    if keywords is not None:
        _register_keyword_routes(app, keywords)
    return app


def automation_soon(now: datetime) -> time | None:
    """AUTOMATION_GUARD 안에 시작할 자동 실행 시각. 이미 시작한 실행은 락이 막으므로 보지 않는다."""
    for start in AUTOMATION_TIMES:
        at = datetime.combine(now.date(), start)
        if at <= now:
            at += timedelta(days=1)
        if at - now < AUTOMATION_GUARD:
            return start
    return None


def _refuse_near_automation(clock: Callable[[], datetime]) -> bool:
    soon = automation_soon(clock())
    if soon is not None:
        flash(f"곧 {soon:%H:%M} 자동 실행이 있어 발행하지 않았습니다 — 겹치면 자동 실행이 "
              "건너뛰어집니다. 그 실행이 끝난 뒤 다시 시도하세요.", "error")
    return soon is not None


def _csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return str(session["csrf_token"])


def safe_url(value: str) -> str:
    """http/https 절대 URL만 링크로 허용 (시트 데이터의 javascript: 등 차단)."""
    parts = urlsplit((value or "").strip())
    return parts.geturl() if parts.scheme.lower() in SAFE_URL_SCHEMES and parts.netloc else ""


def _register_guards(
    app: Flask, allowed_hosts: frozenset[str] | None, brand_label: str,
) -> None:
    app.jinja_env.globals["csrf_token"] = _csrf_token
    app.jinja_env.globals["brand_label"] = brand_label
    app.jinja_env.globals["editing_enabled"] = False
    app.jinja_env.globals["preview_enabled"] = False
    app.jinja_env.globals["draft_enabled"] = False
    app.jinja_env.globals["keywords_enabled"] = False
    app.jinja_env.globals["generate_enabled"] = False
    app.jinja_env.globals["job_labels"] = JOB_LABELS
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


def _register_dashboard_routes(
    app: Flask, reader: PostReader, runner: PublishJobRunner, clock: Callable[[], datetime],
) -> None:
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
        if _refuse_near_automation(clock):
            return redirect(url_for("post_detail", row_index=row_index))
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


def _register_check_routes(
    app: Flask,
    reader: PostReader,
    runner: PublishJobRunner,
    preview: Callable[[PostSummary], str] | None,
    clock: Callable[[], datetime],
) -> None:
    """발행 전 점검: 미리보기(변환 HTML)와 임시저장 시험(실제 에디터, 시트 변경 없음)."""
    app.jinja_env.globals["preview_enabled"] = preview is not None
    app.jinja_env.globals["draft_enabled"] = runner.enabled("draft")
    app.jinja_env.globals["generate_enabled"] = runner.enabled("generate")
    app.jinja_env.globals["revise_enabled"] = runner.enabled("revise")

    @app.post("/posts/<int:row_index>/revise")
    def revise_post(row_index: int):  # type: ignore[no-untyped-def]
        if not runner.enabled("revise") or reader.get(row_index) is None:
            abort(404)
        if _refuse_near_automation(clock):
            return redirect(url_for("post_detail", row_index=row_index))
        job_id = runner.submit(row_index, kind="revise")
        if job_id is None:
            flash("이미 진행 중인 작업이 있습니다. 끝난 뒤 다시 시도하세요.", "error")
            return redirect(url_for("post_detail", row_index=row_index))
        return redirect(url_for("job_status", job_id=job_id))

    @app.post("/generate")
    def generate_posts():  # type: ignore[no-untyped-def]
        if not runner.enabled("generate"):
            abort(404)
        job_id = runner.submit(0, kind="generate")
        if job_id is None:
            flash("이미 진행 중인 작업이 있습니다. 끝난 뒤 다시 시도하세요.", "error")
            return redirect(url_for("index"))
        return redirect(url_for("job_status", job_id=job_id))

    @app.get("/posts/<int:row_index>/preview")
    def preview_post(row_index: int):  # type: ignore[no-untyped-def]
        post = reader.get(row_index)
        if preview is None or post is None:
            abort(404)
        # preview는 허용 태그만 남긴 HTML을 돌려준다(naver/preview.py) — 그래서 safe로 렌더
        return render_template("preview.html", post=post, body_html=preview(post))

    @app.post("/posts/<int:row_index>/draft")
    def draft_post(row_index: int):  # type: ignore[no-untyped-def]
        if not runner.enabled("draft") or reader.get(row_index) is None:
            abort(404)
        if _refuse_near_automation(clock):
            return redirect(url_for("post_detail", row_index=row_index))
        job_id = runner.submit(row_index, kind="draft")
        if job_id is None:
            flash("이미 진행 중인 작업이 있습니다. 끝난 뒤 다시 시도하세요.", "error")
            return redirect(url_for("post_detail", row_index=row_index))
        return redirect(url_for("job_status", job_id=job_id))


def _register_keyword_routes(app: Flask, desk: KeywordDesk) -> None:
    app.jinja_env.globals["keywords_enabled"] = True

    @app.get("/keywords")
    def keywords():  # type: ignore[no-untyped-def]
        return render_template(
            "keywords.html", suggestions=desk.suggest(), source=desk.source,
            max_length=KEYWORD_MAX_LENGTH,
        )

    @app.post("/keywords")
    def register_keyword():  # type: ignore[no-untyped-def]
        keyword = request.form.get("keyword", "").strip()
        if not keyword or len(keyword) > KEYWORD_MAX_LENGTH:
            abort(400, description=f"키워드는 1~{KEYWORD_MAX_LENGTH}자여야 합니다")
        try:
            row = desk.register(keyword)
        except DuplicateKeywordError as e:
            flash(f"등록하지 않았습니다 — {e}", "error")
        else:
            flash(
                f"{row}행에 '{keyword}'을(를) '대기'로 등록했습니다. "
                "생성은 n8n 02:00 실행 때 됩니다.", "success",
            )
        return redirect(url_for("keywords"))


# 편집 폼 입력 상한 — 필수 여부와 최대 글자 수
EDIT_FIELDS = {"title": (True, 150), "body": (True, 30000), "tags": (False, 500),
               "category": (False, 50)}


def _edit_form() -> dict[str, str] | None:
    values = {name: request.form.get(name, "").strip() for name in EDIT_FIELDS}
    for name, (required, limit) in EDIT_FIELDS.items():
        if (required and not values[name]) or len(values[name]) > limit:
            return None
    return values


def _register_edit_routes(app: Flask, editor: EditPostUseCase) -> None:
    app.jinja_env.globals["editing_enabled"] = True

    @app.post("/posts/<int:row_index>/edit")
    def edit_post(row_index: int):  # type: ignore[no-untyped-def]
        values = _edit_form()
        if values is None:
            abort(400, description="제목과 본문은 필수이고, 글자 수 상한을 넘을 수 없습니다")
        try:
            post = editor.edit(row_index, **values)
        except PostNotEditableError:
            abort(409, description="발행·수정 중인 글은 고칠 수 없습니다")
        if post.status == PostStatus.REVISION_PENDING:
            flash("저장하고 수정대기로 바꿨습니다. '수정 발행'을 눌러야 블로그 글에 반영됩니다.",
                  "success")
        else:
            flash("저장했습니다. 발행 전에 본문을 다시 확인하세요.", "success")
        return redirect(url_for("post_detail", row_index=row_index))

    @app.post("/posts/<int:row_index>/restore")
    def restore_post(row_index: int):  # type: ignore[no-untyped-def]
        try:
            editor.restore(row_index)
        except (PostNotEditableError, InvalidStatusTransitionError):
            abort(409, description="발행실패·보류 글만 되돌릴 수 있습니다")
        flash("발행대기로 되돌렸습니다.", "success")
        return redirect(url_for("post_detail", row_index=row_index))
