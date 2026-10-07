"""대시보드 '지금 생성' — n8n CLI로 네이버 워크플로를 한 번 실행하고 결과를 요약."""
from src.interface.web.generation import find_workflow_id, summarize_run

LIST_OUTPUT = """Permissions 0644 for n8n settings file are too wide.
(node:26) [DEP0040] DeprecationWarning: The `punycode` module is deprecated.
ty52rqOEJ6ZjNF2L|Blog Automation Pipeline A — Content Generation
SGXJWwyw6GW5aN6w|Blog Automation Pipeline A — Naver
"""


def test_이름으로_워크플로_ID를_찾는다():
    assert find_workflow_id(LIST_OUTPUT, "Blog Automation Pipeline A — Naver") == "SGXJWwyw6GW5aN6w"


def test_없으면_빈_문자열():
    assert find_workflow_id(LIST_OUTPUT, "없는 워크플로") == ""


def test_성공하면_늘어난_발행대기_수를_알려준다():
    ok, message = summarize_run(
        0, "Execution was successful:\n{...}", pending_before=1, pending_after=3,
    )
    assert ok and "발행대기 3건" in message and "+2" in message


def test_대기_키워드가_없어_새_글이_없으면_그렇게_알려준다():
    ok, message = summarize_run(0, "Execution was successful:", pending_before=2, pending_after=2)
    assert ok and "새로 만든 글 없음" in message


def test_중복으로_건너뛴_키워드를_알려준다():
    # 새 글이 없을 때 "'대기' 키워드가 있는지 확인"만 보이면 중복 판정을 알 수 없다
    ok, message = summarize_run(
        0, "Execution was successful:", pending_before=1, pending_after=1,
        skipped=["Claude vs ChatGPT 업무용"],
    )
    assert ok and "중복으로 건너뜀 1건" in message and "Claude vs ChatGPT 업무용" in message
    assert "'대기' 키워드가 있는지" not in message


def test_실패하면_출력_끝부분을_사유로():
    ok, message = summarize_run(1, "...\nError: SerpAPI 429 Too Many Requests", 0, 0)
    assert not ok and "SerpAPI 429" in message


class _Run:
    def __init__(self, stdout=""):
        self.returncode, self.stdout, self.stderr = 0, stdout, ""


def _fake_n8n(monkeypatch, fail=False):
    from src.interface.web import generation

    def run(cmd, **kwargs):
        if "execute" in cmd and fail:
            raise TimeoutError("n8n 응답 없음")
        return _Run("ID1|wf\n" if "list:workflow" in cmd else "")

    monkeypatch.setattr(generation.subprocess, "run", run)


def test_글_하나만_생성할_때는_생성요청_표시를_달았다가_지운다(monkeypatch):
    from src.interface.web.generation import build_generator

    _fake_n8n(monkeypatch)
    marks: list[tuple[int, str]] = []
    build_generator("c", "wf", lambda: (0, set()), mark=lambda r, v: marks.append((r, v)))(7)
    assert marks == [(7, "생성요청"), (7, "")]


def test_전체_생성은_표시하지_않는다(monkeypatch):
    from src.interface.web.generation import build_generator

    _fake_n8n(monkeypatch)
    marks: list[tuple[int, str]] = []
    build_generator("c", "wf", lambda: (0, set()), mark=lambda r, v: marks.append((r, v)))(0)
    assert marks == []


def test_실행이_실패해도_표시를_지운다(monkeypatch):
    # 남은 표시는 다음 예약 실행이 그 행만 처리하게 만든다
    import pytest

    from src.interface.web.generation import build_generator

    _fake_n8n(monkeypatch, fail=True)
    marks: list[tuple[int, str]] = []
    with pytest.raises(TimeoutError):
        build_generator("c", "wf", lambda: (0, set()), mark=lambda r, v: marks.append((r, v)))(7)
    assert marks[-1] == (7, "")
