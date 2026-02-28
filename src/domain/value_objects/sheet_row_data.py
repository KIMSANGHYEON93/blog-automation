"""SheetRowData — Value Object representing a single row from Google Sheets."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SheetRowData:
    row_index: int
    keyword: str
    category: str = ""
    content_type: str = ""
    status: str = ""
    generated_title: str = ""
    generated_body: str = ""
    meta_description: str = ""
    faq_schema: str = ""
    internal_link_keywords: str = ""
    published_url: str = ""
    published_at: str | None = None
    note: str = ""
