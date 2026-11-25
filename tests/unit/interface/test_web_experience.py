"""상세 화면 '직접 해 보니' 빠른 입력 — 미리보기 후 저장, JS 없이, CSRF 검사."""
from __future__ import annotations

import html as html_lib
import re

import pytest

from src.domain.value_objects.post_content import PostContent
from tests.unit.interface.test_web_app import Harness

MARKER = "[[직접 해 보니]] 해 보고 답해 주세요. 확인할 것: 요약이 됐나요? 몇 분까지 됐나요?"
BODY = "## 설정\n\n" + "가" * 3200 + f"\n\n{MARKER}\n\n## 자주 묻는 질문\n\nQ. 무료?"
URL = "/posts/2/experience"


@pytest.fixture
def h() -> Harness:
    harness = Harness(photo_store=lambda data: "a1.jpg")
    _post(harness).content = PostContent(title="제목", body_markdown=BODY)
    harness.login()
    return harness


def _post(h):
    return next(p for p in h.repo.find_all() if p.row_index == 2)


def _send(h, action, result="worked", answers=("예", "30분"), memo="", **extra):
    data = {"csrf_token": h.csrf("/posts/2"), "action": action, "result": result,
            "answer": list(answers), "memo": memo, **extra}
    return h.client.post(URL, data=data)


def _previewed(page: str) -> str:
    match = re.search(r'name="previewed" value="([^"]+)"', page)
    assert match, "미리보기 지문 없음"
    return match.group(1)


def test_표시가_있으면_질문과_결과_선택이_보인다(h):
    page = h.client.get("/posts/2").get_data(as_text=True)
    assert f'action="{URL}"' in page
    assert "요약이 됐나요?" in page and "몇 분까지 됐나요?" in page
    assert page.count('type="radio" name="result"') == 3
    assert 'href="#photo"' in page and 'id="photo"' in page  # 기존 '사진 올리기' 재사용
    assert 'value="save"' not in page  # 미리보기 전에는 저장 버튼이 없다
    assert "<script" not in page


def test_표시가_없으면_빠른_입력이_없다(h):
    _post(h).content = PostContent(title="제목", body_markdown="가" * 3200)
    assert f'action="{URL}"' not in h.client.get("/posts/2").get_data(as_text=True)


def test_미리보기는_조립한_문단을_보여주고_저장하지_않는다(h):
    resp = _send(h, "preview", result="partial", memo="화자 3명은 섞임")
    page = html_lib.unescape(resp.get_data(as_text=True))
    assert resp.status_code == 200
    assert "이 글의 방법을 제가 직접 해 봤고, 일부만 됐습니다. 화자 3명은 섞임" in page
    assert "- 몇 분까지 됐나요? → 30분" in page
    assert 'value="partial" checked' in page and 'value="30분"' in page  # 입력 유지
    assert 'value="save"' in page
    assert _post(h).content.body_markdown == BODY


def test_미리보기한_그대로_저장하면_표시가_바뀌고_상세로_돌아간다(h):
    previewed = _previewed(_send(h, "preview").get_data(as_text=True))
    resp = _send(h, "save", previewed=previewed)
    assert resp.status_code == 302 and resp.headers["Location"] == "/posts/2"
    body = _post(h).content.body_markdown
    assert "[[직접 해 보니]]" not in body and "- 요약이 됐나요? → 예" in body
    assert _post(h).publish_blockers() == []


def test_미리보기_뒤_입력을_바꾸면_저장하지_않고_다시_보여준다(h):
    previewed = _previewed(_send(h, "preview").get_data(as_text=True))
    resp = _send(h, "save", answers=("예", "45분"), previewed=previewed)
    page = html_lib.unescape(resp.get_data(as_text=True))
    assert resp.status_code == 200 and "→ 45분" in page and "다시 확인" in page
    assert _post(h).content.body_markdown == BODY


@pytest.mark.parametrize("result, answers", [
    ("", ("예", "30분")),
    ("hack", ("예", "30분")),
    ("worked", ("예", " ")),
    ("worked", ("예",)),
])
def test_결과나_답이_비면_저장하지_않고_이유를_보여준다(h, result, answers):
    resp = _send(h, "save", result=result, answers=answers, previewed="x")
    assert resp.status_code == 400
    assert 'class="notice notice-error"' in resp.get_data(as_text=True)
    assert _post(h).content.body_markdown == BODY
    assert any("직접 해 보니" in r for r in _post(h).publish_blockers())


def test_CSRF_토큰이_없으면_거부한다(h):
    resp = h.client.post(URL, data={"action": "save", "result": "worked", "answer": ["예", "1"]})
    assert resp.status_code == 400
    assert _post(h).content.body_markdown == BODY


def test_로그인하지_않으면_로그인_화면으로(h):
    h.client.post("/logout", data={"csrf_token": h.csrf("/posts/2")})
    assert h.client.get("/posts/2").status_code == 302
