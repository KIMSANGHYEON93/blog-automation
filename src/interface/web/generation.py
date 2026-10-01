"""대시보드 '지금 생성' — n8n 컨테이너의 CLI로 네이버 워크플로를 한 번 실행한다.

웹훅 대신 CLI를 쓰는 이유: 웹훅은 워크플로를 활성화해야 동작하는데, 활성화하면 02:00
스케줄도 켜진다. CLI는 비활성 워크플로도 실행하고 외부에 새 입구를 열지 않는다.
"""
from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence

from src.application.use_cases.publish_selected_post import (
    ManualPublishOutcome,
    ManualPublishResult,
)

N8N_TIMEOUT_SECONDS = 900  # 대기 키워드 여러 건이면 LLM 호출이 길다
# scripts/build_naver_workflow.py 의 WORKFLOW_NAME과 같아야 한다(테스트가 확인)
NAVER_WORKFLOW_NAME = "Blog Automation Pipeline A — Naver"
DEFAULT_N8N_CONTAINER = "blog-automation-n8n-1"


def find_workflow_id(list_output: str, name: str) -> str:
    """`n8n list:workflow` 출력("ID|이름" 줄)에서 이름이 같은 워크플로 ID."""
    for line in list_output.splitlines():
        workflow_id, sep, workflow_name = line.partition("|")
        if sep and workflow_name.strip() == name:
            return workflow_id.strip()
    return ""


def summarize_run(
    returncode: int, stdout: str, pending_before: int, pending_after: int,
    skipped: Sequence[str] = (),
) -> tuple[bool, str]:
    if returncode != 0 or "Execution was successful" not in stdout:
        tail = " ".join(stdout.strip().splitlines()[-3:])[-300:]
        return False, f"생성 실패 — {tail or f'n8n 종료 코드 {returncode}'}"
    added = pending_after - pending_before
    note = f" · 중복으로 건너뜀 {len(skipped)}건: {', '.join(skipped)}" if skipped else ""
    if added <= 0:
        hint = "" if skipped else ". '대기' 키워드가 있는지 확인하세요"
        return True, f"생성 완료 — 새로 만든 글 없음(발행대기 {pending_after}건){note}{hint}"
    return True, f"생성 완료 — 발행대기 {pending_after}건 (+{added}){note}"


def build_generator(
    container: str, workflow_name: str, snapshot: Callable[[], tuple[int, set[str]]],
) -> Callable[[int], ManualPublishResult]:
    """snapshot() → (발행대기 수, 중복으로 건너뛴 키워드). 실행 전후 차이로 결과를 알린다."""
    def generate(_row_index: int) -> ManualPublishResult:
        listed = subprocess.run(
            ["docker", "exec", container, "n8n", "list:workflow"],
            capture_output=True, text=True, timeout=60,
        )
        workflow_id = find_workflow_id(listed.stdout, workflow_name)
        if not workflow_id:
            return ManualPublishResult.failed(0, f"n8n에 '{workflow_name}' 워크플로가 없습니다")
        pending_before, skipped_before = snapshot()
        run = subprocess.run(
            ["docker", "exec", container, "n8n", "execute", "--id", workflow_id],
            capture_output=True, text=True, timeout=N8N_TIMEOUT_SECONDS,
        )
        pending_after, skipped_after = snapshot()
        ok, message = summarize_run(
            run.returncode, run.stdout + run.stderr, pending_before, pending_after,
            sorted(skipped_after - skipped_before),
        )
        outcome = ManualPublishOutcome.GENERATED if ok else ManualPublishOutcome.FAILED
        return ManualPublishResult(outcome, 0, message)

    return generate
