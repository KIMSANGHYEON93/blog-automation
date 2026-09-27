"""PublishJobRunner — 수동 발행을 백그라운드 스레드에서 실행 (브라우저 1개라 동시에 1건만)."""
from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Callable

from src.application.use_cases.publish_selected_post import ManualPublishResult

logger = logging.getLogger(__name__)

MAX_RECENT_JOBS = 20


class JobState(Enum):
    RUNNING = "running"
    DONE = "done"


@dataclass(frozen=True)
class PublishJob:
    job_id: str
    row_index: int
    state: JobState
    started_at: datetime
    finished_at: datetime | None = None
    result: ManualPublishResult | None = None
    draft: bool = False


class PublishJobRunner:
    """발행과 임시저장 시험은 같은 브라우저를 쓰므로 한 실행기에서 동시에 1건만 돈다."""

    def __init__(
        self,
        publish: Callable[[int], ManualPublishResult],
        draft: Callable[[int], ManualPublishResult] | None = None,
    ):
        self._publish = publish
        self.draft_enabled = draft is not None
        self._draft = draft
        self._jobs: OrderedDict[str, PublishJob] = OrderedDict()
        self._events: dict[str, threading.Event] = {}
        self._active_id: str | None = None
        self._mutex = threading.Lock()

    def submit(self, row_index: int, draft: bool = False) -> str | None:
        """작업 시작. 이미 실행 중인 작업이 있으면 None."""
        with self._mutex:
            if self._active_id is not None:
                return None
            job = PublishJob(
                uuid.uuid4().hex, row_index, JobState.RUNNING, datetime.now(), draft=draft,
            )
            self._jobs[job.job_id] = job
            self._events[job.job_id] = threading.Event()
            self._active_id = job.job_id
            while len(self._jobs) > MAX_RECENT_JOBS:
                old_id, _ = self._jobs.popitem(last=False)
                self._events.pop(old_id, None)
        worker = threading.Thread(
            target=self._run, args=(job,), name=f"publish-{row_index}", daemon=True,
        )
        worker.start()
        return job.job_id

    def get(self, job_id: str) -> PublishJob | None:
        with self._mutex:
            return self._jobs.get(job_id)

    def active_job(self) -> PublishJob | None:
        with self._mutex:
            return self._jobs.get(self._active_id) if self._active_id else None

    def recent(self) -> list[PublishJob]:
        with self._mutex:
            return list(reversed(self._jobs.values()))

    def wait(self, job_id: str, timeout: float) -> PublishJob | None:
        event = self._events.get(job_id)
        if event:
            event.wait(timeout)
        return self.get(job_id)

    def _run(self, job: PublishJob) -> None:
        try:
            run = self._draft if job.draft and self._draft else self._publish
            result = run(job.row_index)
        except Exception as e:
            logger.exception(f"수동 발행 작업 예외: row={job.row_index}")
            result = ManualPublishResult.failed(job.row_index, f"{type(e).__name__}: {e}")
        with self._mutex:
            self._jobs[job.job_id] = replace(
                job, state=JobState.DONE, finished_at=datetime.now(), result=result,
            )
            self._active_id = None
            event = self._events.get(job.job_id)
        if event:
            event.set()
