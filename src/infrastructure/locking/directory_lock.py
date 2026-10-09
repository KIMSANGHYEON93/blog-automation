"""DirectoryPipelineLock — run_pipeline_b.sh와 같은 mkdir 원자적 락 (PipelineLockPort 구현).

규약(쉘 스크립트와 공유):
- 락 = `.pipeline_b.lock` 디렉터리. 잡은 쪽이 안에 `owner` 파일로 자기 PID를 적는다.
- 스테일 판단: owner가 있으면 그 PID가 죽었을 때(또는 PID 재사용 대비 하루가 넘었을 때)만,
  owner가 없으면(예전 형식) 예전처럼 5시간이 넘었을 때.
- 해제 책임은 잡은 프로세스에만 있다 — owner를 지우고 디렉터리를 지운다.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from src.domain.ports.pipeline_lock_port import PipelineLockPort

logger = logging.getLogger(__name__)

# run_pipeline_b.sh의 `find -mmin +300`과 동일한 스테일 기준 (owner 없는 락)
DEFAULT_STALE_AFTER_SECONDS = 300 * 60
# owner PID가 살아 있어도 이보다 오래되면 PID 재사용으로 본다 (run_pipeline_b.sh `-mmin +1440`)
OWNER_MAX_AGE_SECONDS = 24 * 3600
OWNER_FILE = "owner"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 다른 사용자 프로세스 — 살아 있다
    return True


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
                self._remove()
            except OSError:
                return False
            return self._try_mkdir()
        return False

    def release(self) -> None:
        if not self._held:
            return
        try:
            self._remove()
        except FileNotFoundError:
            pass
        finally:
            self._held = False

    def _remove(self) -> None:
        (self._lock_dir / OWNER_FILE).unlink(missing_ok=True)
        self._lock_dir.rmdir()

    def _try_mkdir(self) -> bool:
        try:
            self._lock_dir.mkdir()
        except FileExistsError:
            return False
        self._held = True
        (self._lock_dir / OWNER_FILE).write_text(str(os.getpid()))
        return True

    def _is_stale(self) -> bool:
        try:
            age = time.time() - self._lock_dir.stat().st_mtime
        except FileNotFoundError:
            return True
        try:
            owner = int((self._lock_dir / OWNER_FILE).read_text().strip())
        except (FileNotFoundError, ValueError):
            return age > self._stale_after  # 예전 형식(owner 없음)
        return not _pid_alive(owner) or age > OWNER_MAX_AGE_SECONDS
