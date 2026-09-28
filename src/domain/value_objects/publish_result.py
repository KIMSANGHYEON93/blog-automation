"""PublishResult — Value Object for publish outcome."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PublishResult:
    success: bool
    url: str = ""
    error: str = ""
    entry_id: str = ""
    warnings: tuple[str, ...] = ()  # 발행은 됐지만 점검에서 걸린 것(카테고리·태그·사진 수 등)

    @classmethod
    def ok(
        cls, url: str, entry_id: str = "", warnings: tuple[str, ...] = (),
    ) -> "PublishResult":
        return cls(success=True, url=url, error="", entry_id=entry_id, warnings=warnings)

    @classmethod
    def fail(cls, error: str) -> "PublishResult":
        return cls(success=False, url="", error=error)
