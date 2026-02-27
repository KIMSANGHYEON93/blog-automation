"""ColumnIndex — Value Object for Google Sheets column mapping (A-S)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnIndex:
    """1-indexed column positions for Google Sheets."""
    no: int = 1
    keyword: int = 2
    category: int = 3
    content_type: int = 4
    search_volume: int = 5
    cpc: int = 6
    difficulty: int = 7
    priority: int = 8
    scheduled_date: int = 9
    status: int = 10
    published_url: int = 11
    published_at: int = 12
    indexed: int = 13
    note: int = 14
    generated_title: int = 15
    generated_body: int = 16
    meta_description: int = 17
    faq_schema: int = 18
    internal_link_keywords: int = 19
