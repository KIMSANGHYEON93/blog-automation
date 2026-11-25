"""상세 화면 '직접 해 보니' 빠른 입력 — 결과·짧은 답·메모로 경험 문단을 채운다.

JS 없이(CSP script-src 'none') 같은 폼을 두 번 보낸다: '미리보기'가 조립한 문단과 그 지문을
보여 주고, '저장'은 지문이 지금 입력으로 만든 문단과 같을 때만 저장한다(미리보기 뒤 입력을
바꿨으면 다시 미리보기). CSRF는 app의 before_request가 모든 POST에 검사한다.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from flask import Flask, abort, flash, redirect, render_template, request, url_for

from src.application.use_cases.edit_post import EditPostUseCase, PostNotEditableError
from src.application.use_cases.list_posts import PostSummary
from src.domain.services.experience_note import (
    MAX_ANSWER_LENGTH,
    MAX_MEMO_LENGTH,
    ExperienceInputError,
    ExperienceResult,
)
from src.domain.value_objects.post_status import PostStatus
from src.interface.web.jobs import PublishJobRunner

# 폼 원본 길이 상한 — 도메인 검사(공백 정리 뒤 길이) 전에 터무니없는 입력을 자른다
_RAW_LIMIT = 500


class _Reader(Protocol):
    def get(self, row_index: int) -> PostSummary | None: ...


@dataclass(frozen=True)
class ExperienceForm:
    """화면에 다시 채울 입력과 미리보기 결과."""
    result: str = ""
    answers: tuple[str, ...] = ()
    memo: str = ""
    preview: str = ""
    error: str = ""
    notice: str = ""

    @property
    def fingerprint(self) -> str:
        return preview_fingerprint(self.preview) if self.preview else ""


def preview_fingerprint(paragraph: str) -> str:
    return hashlib.sha256(paragraph.encode("utf-8")).hexdigest()[:16]


def register_experience_route(
    app: Flask, editor: EditPostUseCase, reader: _Reader, runner: PublishJobRunner,
) -> None:
    app.jinja_env.globals["experience_results"] = tuple(ExperienceResult)
    app.jinja_env.globals["experience_limits"] = (MAX_ANSWER_LENGTH, MAX_MEMO_LENGTH)

    @app.post("/posts/<int:row_index>/experience")
    def fill_experience(row_index: int):  # type: ignore[no-untyped-def]
        raw = _read_form()
        result = ExperienceResult.from_form(raw.result)
        try:
            paragraph = editor.preview_experience(row_index, result, raw.answers, raw.memo)
            if request.form.get("action") != "save":
                return _render(row_index, raw, paragraph=paragraph)
            if request.form.get("previewed", "") != preview_fingerprint(paragraph):
                return _render(row_index, raw, paragraph=paragraph,
                               notice="입력이 미리보기와 달라 저장하지 않았습니다. 다시 확인하고 "
                                      "저장하세요.")
            post = editor.fill_experience(row_index, result, raw.answers, raw.memo)
        except PostNotEditableError:
            abort(409, description="발행·수정 중인 글은 고칠 수 없습니다")
        except ExperienceInputError as e:
            return _render(row_index, raw, error=str(e), status=400)
        flash("경험 문단을 넣었습니다. 발행 전에 본문에서 한 번 더 확인하세요.", "success")
        if post.status == PostStatus.REVISION_PENDING:
            flash("발행된 글이라 수정대기로 바꿨습니다. '수정 발행'을 눌러야 반영됩니다.",
                  "success")
        return redirect(url_for("post_detail", row_index=row_index))

    def _render(row_index: int, raw: ExperienceForm, *, paragraph: str = "", error: str = "",
                notice: str = "", status: int = 200):  # type: ignore[no-untyped-def]
        post = reader.get(row_index)
        if post is None:
            abort(404)
        form = ExperienceForm(raw.result, raw.answers, raw.memo, paragraph, error, notice)
        page = render_template("post_detail.html", post=post, active_job=runner.active_job(),
                               experience=form)
        return page, status


def _read_form() -> ExperienceForm:
    return ExperienceForm(
        result=request.form.get("result", "")[:20],
        answers=tuple(a[:_RAW_LIMIT] for a in request.form.getlist("answer")[:10]),
        memo=request.form.get("memo", "")[:_RAW_LIMIT],
    )
