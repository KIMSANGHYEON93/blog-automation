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


def test_실패하면_출력_끝부분을_사유로():
    ok, message = summarize_run(1, "...\nError: SerpAPI 429 Too Many Requests", 0, 0)
    assert not ok and "SerpAPI 429" in message
