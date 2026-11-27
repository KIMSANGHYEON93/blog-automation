"""'직접 해 보니' 빠른 입력 — 사람이 고른 결과와 짧은 답만으로 경험 문단을 조립한다.

LLM을 쓰지 않는 템플릿 조립이다. 문단에 들어가는 사실은 입력(결과·답·메모)뿐이고,
질문 문장은 초안의 '확인할 것'을 그대로 옮긴다 — 입력에 없는 경험·수치를 만들지 않는다
(네이버 AI 콘텐츠 가이드 2026-05의 사람 검수 요건).
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from enum import Enum

# n8n 네이버 초안(prompt_naver_common.md)이 사람의 경험을 채울 자리에 남기는 표시
EXPERIENCE_PLACEHOLDER = "[[직접 해 보니]]"
FALLBACK_QUESTION = "이 글의 방법 중 무엇을 해 봤나요?"
MAX_QUESTIONS = 3
MAX_ANSWER_LENGTH = 60
MAX_MEMO_LENGTH = 120

_MARKER_LINE = re.compile(r"^[^\n]*" + re.escape(EXPERIENCE_PLACEHOLDER) + r"[^\n]*$", re.M)
_CHECK_LABEL = "확인할 것:"
_QUESTION = re.compile(r"[^?？]+[?？]")
_SEPARATORS = " \t/,·;"
# 본문의 표시 문법 — 답에 섞이면 사진 자리·자리표시로 잘못 읽힌다
_FORBIDDEN = ("[[", "]]", "<!--", "-->")


class ExperienceInputError(ValueError):
    """빠른 입력을 문단으로 만들 수 없다 — 메시지는 화면에 그대로 보인다."""


class ExperienceResult(Enum):
    WORKED = "worked"
    PARTIAL = "partial"
    FAILED = "failed"

    @classmethod
    def from_form(cls, value: str) -> ExperienceResult | None:
        return next((r for r in cls if r.value == value), None)

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def sentence(self) -> str:
        return _SENTENCES[self]


_LABELS = {
    ExperienceResult.WORKED: "됐음",
    ExperienceResult.PARTIAL: "일부만",
    ExperienceResult.FAILED: "안 됐음",
}
_SENTENCES = {
    ExperienceResult.WORKED: "이 글의 방법을 제가 직접 해 봤고, 그대로 됐습니다.",
    ExperienceResult.PARTIAL: "이 글의 방법을 제가 직접 해 봤고, 일부만 됐습니다.",
    ExperienceResult.FAILED: "이 글의 방법을 제가 직접 해 봤지만, 그대로는 되지 않았습니다.",
}


def experience_questions(markdown: str) -> list[str]:
    """표시 문단의 '확인할 것' 질문들. 물음표가 없는 예전 자유 형식은 통째로 한 질문."""
    line = _MARKER_LINE.search(markdown)
    if line is None:
        return []
    _, label, rest = line.group(0).partition(_CHECK_LABEL)
    if not label or not rest.strip():
        return [FALLBACK_QUESTION]
    found = [q.strip(_SEPARATORS) for q in _QUESTION.findall(rest)]
    questions = [q for q in found if q.rstrip("?？").strip()]
    if not questions:
        return [rest.strip(_SEPARATORS + ".")]
    return questions[:MAX_QUESTIONS]


def compose_experience_paragraph(
    result: ExperienceResult | None,
    answers: Sequence[tuple[str, str]],
    memo: str,
) -> str:
    """결과 한 문장(+메모) 뒤에 '질문 → 답' 목록. 답이 하나라도 비면 거절한다."""
    if result is None:
        raise ExperienceInputError("결과(됐음·일부만·안 됐음)를 골라 주세요")
    if not answers:
        raise ExperienceInputError("답할 질문이 없습니다 — 화면을 새로 고쳐 주세요")
    lines = []
    for question, raw in answers:
        answer = _clean(raw)
        if not answer:
            raise ExperienceInputError(f"답이 비어 있습니다: {question}")
        if len(answer) > MAX_ANSWER_LENGTH:
            raise ExperienceInputError(f"답은 {MAX_ANSWER_LENGTH}자 이내로 짧게 적어 주세요")
        lines.append(f"- {question} → {answer}")
    note = _clean(memo)
    if len(note) > MAX_MEMO_LENGTH:
        raise ExperienceInputError(f"메모는 {MAX_MEMO_LENGTH}자 이내로 적어 주세요")
    first = f"{result.sentence} {note}" if note else result.sentence
    return first + "\n\n" + "\n".join(lines)


def fill_experience(markdown: str, paragraph: str) -> str:
    """표시가 있는 줄 하나를 조립한 문단으로 바꾼다."""
    if _MARKER_LINE.search(markdown) is None:
        raise ExperienceInputError("이미 채워졌거나 '직접 해 보니' 표시가 없습니다")
    return _MARKER_LINE.sub(lambda _: paragraph, markdown, count=1)


def _clean(text: str) -> str:
    """한 줄로 모으고 앞뒤 공백을 뺀다. 표시 문법이 섞이면 거절한다."""
    one_line = " ".join((text or "").split())
    if any(token in one_line for token in _FORBIDDEN):
        raise ExperienceInputError("답과 메모에는 [[ ]]·<!-- --> 표시를 넣을 수 없습니다")
    return one_line
