"""SheetRowData — Value Object representing a single row from Google Sheets."""
from dataclasses import dataclass
from typing import Optional


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
    published_at: Optional[str] = None
    note: str = ""
