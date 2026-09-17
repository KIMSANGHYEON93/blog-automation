"""DirectoryPipelineLock — run_pipeline_b.sh와 같은 mkdir 락 규약."""
from __future__ import annotations

import os
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
