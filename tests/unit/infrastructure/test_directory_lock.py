"""DirectoryPipelineLock — run_pipeline_b.sh와 같은 mkdir 락 규약."""
from __future__ import annotations

import os
import subprocess
import time

from src.infrastructure.locking.directory_lock import DirectoryPipelineLock


class TestDirectoryPipelineLock:
    def test_획득하면_디렉터리_생성_해제하면_삭제(self, tmp_path):
        lock_dir = tmp_path / ".pipeline_b.lock"
        lock = DirectoryPipelineLock(lock_dir)
        assert lock.acquire() is True
        assert lock_dir.is_dir()
        lock.release()
        assert not lock_dir.exists()

    def test_다른_실행이_잡고_있으면_획득_실패(self, tmp_path):
        lock_dir = tmp_path / ".pipeline_b.lock"
        lock_dir.mkdir()  # 쉘 스크립트가 잡은 상태
        lock = DirectoryPipelineLock(lock_dir)
        assert lock.acquire() is False
        lock.release()  # 획득하지 않은 락은 지우지 않음
        assert lock_dir.is_dir()

    def test_오래된_스테일_락은_해제_후_획득(self, tmp_path):
        lock_dir = tmp_path / ".pipeline_b.lock"
        lock_dir.mkdir()
        old = time.time() - 6 * 3600
        os.utime(lock_dir, (old, old))
        lock = DirectoryPipelineLock(lock_dir, stale_after_seconds=5 * 3600)
        assert lock.acquire() is True

    def test_같은_인스턴스_중복_획득_불가(self, tmp_path):
        lock = DirectoryPipelineLock(tmp_path / ".pipeline_b.lock")
        assert lock.acquire() is True
        assert lock.acquire() is False


class TestLockOwner:
    """경과 시간만으로 살아 있는 작업의 락을 지우지 않는다 — 소유 PID를 기록·확인."""

    def test_획득하면_소유_PID_기록_해제하면_디렉터리째_삭제(self, tmp_path):
        lock_dir = tmp_path / ".pipeline_b.lock"
        lock = DirectoryPipelineLock(lock_dir)
        assert lock.acquire() is True
        assert (lock_dir / "owner").read_text().strip() == str(os.getpid())
        lock.release()
        assert not lock_dir.exists()

    def test_오래됐어도_소유_프로세스가_살아_있으면_빼앗지_않는다(self, tmp_path):
        lock_dir = tmp_path / ".pipeline_b.lock"
        lock_dir.mkdir()
        (lock_dir / "owner").write_text(str(os.getpid()))
        old = time.time() - 6 * 3600
        os.utime(lock_dir, (old, old))
        assert DirectoryPipelineLock(lock_dir, stale_after_seconds=5 * 3600).acquire() is False

    def test_소유_프로세스가_죽었으면_바로_회수(self, tmp_path):
        proc = subprocess.Popen(["true"])
        proc.wait()
        lock_dir = tmp_path / ".pipeline_b.lock"
        lock_dir.mkdir()
        (lock_dir / "owner").write_text(str(proc.pid))
        lock = DirectoryPipelineLock(lock_dir)
        assert lock.acquire() is True
        assert (lock_dir / "owner").read_text().strip() == str(os.getpid())

    def test_PID가_살아_있어도_하루가_넘으면_재사용으로_보고_회수(self, tmp_path):
        lock_dir = tmp_path / ".pipeline_b.lock"
        lock_dir.mkdir()
        (lock_dir / "owner").write_text(str(os.getpid()))
        old = time.time() - 25 * 3600
        os.utime(lock_dir, (old, old))
        assert DirectoryPipelineLock(lock_dir).acquire() is True
