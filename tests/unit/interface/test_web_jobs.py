"""PublishJobRunner — 수동 발행 백그라운드 작업 (동시에 1건만)."""
from __future__ import annotations

import threading

from src.application.use_cases.publish_selected_post import (
    ManualPublishOutcome,
    ManualPublishResult,
)
from src.interface.web.jobs import JobState, PublishJobRunner


def _ok(row: int) -> ManualPublishResult:
    return ManualPublishResult(ManualPublishOutcome.PUBLISHED, row, "발행 완료", url=f"https://b/{row}")


class TestPublishJobRunner:
    def test_작업_완료_후_결과_조회(self):
        runner = PublishJobRunner(publish=_ok)
        job_id = runner.submit(row_index=7)
        job = runner.wait(job_id, timeout=5)
        assert job.state == JobState.DONE
        assert job.row_index == 7
        assert job.result.url == "https://b/7"

    def test_실행_중에는_새_작업_거부(self):
        release = threading.Event()

        def slow(row: int) -> ManualPublishResult:
            release.wait(5)
            return _ok(row)

        runner = PublishJobRunner(publish=slow)
        first = runner.submit(row_index=1)
        assert first is not None
        assert runner.submit(row_index=2) is None
        assert runner.active_job().row_index == 1
        release.set()
        runner.wait(first, timeout=5)
        assert runner.active_job() is None
        assert runner.submit(row_index=2) is not None

    def test_예외는_실패_결과로_기록(self):
        def boom(row: int) -> ManualPublishResult:
            raise RuntimeError("sheets down")

        runner = PublishJobRunner(publish=boom)
        job = runner.wait(runner.submit(row_index=3), timeout=5)
        assert job.state == JobState.DONE
        assert job.result.outcome == ManualPublishOutcome.FAILED
        assert "sheets down" in job.result.message

    def test_없는_작업_조회(self):
        assert PublishJobRunner(publish=_ok).get("nope") is None

    def test_최근_작업_목록은_최신순(self):
        runner = PublishJobRunner(publish=_ok)
        for row in (1, 2):
            runner.wait(runner.submit(row_index=row), timeout=5)
        assert [j.row_index for j in runner.recent()] == [2, 1]
