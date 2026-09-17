"""DirectoryPipelineLock — run_pipeline_b.sh와 같은 mkdir 원자적 락 (PipelineLockPort 구현)."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from src.domain.ports.pipeline_lock_port import PipelineLockPort

logger = logging.getLogger(__name__)

# run_pipeline_b.sh의 `find -mmin +300`과 동일한 스테일 기준
DEFAULT_STALE_AFTER_SECONDS = 300 * 60


class DirectoryPipelineLock(PipelineLockPort):
    def __init__(self, lock_dir: Path, stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS):
        self._lock_dir = Path(lock_dir)
        self._stale_after = stale_after_seconds
        self._held = False

    def acquire(self) -> bool:
        if self._held:
            return False
        if self._try_mkdir():
            return True
        if self._is_stale():
            logger.warning(f"스테일 파이프라인 락 해제: {self._lock_dir}")
            try:
                self._lock_dir.rmdir()
            except OSError:
                return False
            return self._try_mkdir()
        return False

    def release(self) -> None:
        if not self._held:
            return
        try:
            self._lock_dir.rmdir()
        except FileNotFoundError:
            pass
        finally:
            self._held = False

    def _try_mkdir(self) -> bool:
        try:
            self._lock_dir.mkdir()
        except FileExistsError:
            return False
        self._held = True
        return True

    def _is_stale(self) -> bool:
        try:
            age = time.time() - self._lock_dir.stat().st_mtime
        except FileNotFoundError:
            return True
        return age > self._stale_after
