"""PublishResult — Value Object for publish outcome."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PublishResult:
    success: bool
    url: str = ""
    error: str = ""
    entry_id: str = ""

    @classmethod
    def ok(cls, url: str, entry_id: str = "") -> "PublishResult":
        return cls(success=True, url=url, error="", entry_id=entry_id)

    @classmethod
    def fail(cls, error: str) -> "PublishResult":
        return cls(success=False, url="", error=error)
