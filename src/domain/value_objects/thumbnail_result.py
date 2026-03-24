"""ThumbnailResult — Value Object for thumbnail generation/upload result."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThumbnailResult:
    success: bool
    image_url: str = ""
    error: str = ""
    row_index: int = 0
    keyword: str = ""

    @classmethod
    def ok(cls, image_url: str, row_index: int = 0, keyword: str = "") -> ThumbnailResult:
        return cls(success=True, image_url=image_url, row_index=row_index, keyword=keyword)

    @classmethod
    def fail(cls, error: str, row_index: int = 0, keyword: str = "") -> ThumbnailResult:
        return cls(success=False, error=error, row_index=row_index, keyword=keyword)
