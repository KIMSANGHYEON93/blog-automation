"""PostContent — Value Object for blog post content."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PostContent:
    title: str | None = ""
    body_markdown: str | None = ""
    meta_description: str = ""
    faq_schema: str = ""

    def has_body(self) -> bool:
        return bool(self.body_markdown and self.body_markdown.strip())

    def title_or_fallback(self, fallback: str) -> str:
        if self.title and self.title.strip():
            return self.title
        return fallback
