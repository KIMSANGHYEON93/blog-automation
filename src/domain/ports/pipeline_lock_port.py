"""PipelineLockPort — 발행 파이프라인 동시 실행 방지 (자동 실행 ↔ 수동 발행)."""
from __future__ import annotations

from abc import ABC, abstractmethod


class PipelineLockPort(ABC):
    @abstractmethod
    def acquire(self) -> bool:
        """락 획득 시도. 다른 실행이 진행 중이면 False."""
        ...

    @abstractmethod
    def release(self) -> None:
        """획득한 락 해제."""
        ...
