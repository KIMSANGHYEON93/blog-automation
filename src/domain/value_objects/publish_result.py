"""PublishResult — Value Object for publish outcome."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PublishResult:
    success: bool
    url: str = ""
    error: str = ""

    @classmethod
    def ok(cls, url: str) -> "PublishResult":
        return cls(success=True, url=url, error="")

    @classmethod
    def fail(cls, error: str) -> "PublishResult":
        return cls(success=False, url="", error=error)
