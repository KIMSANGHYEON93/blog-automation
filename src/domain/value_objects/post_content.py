"""PostContent — Value Object for blog post content."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PostContent:
    title: Optional[str] = ""
    body_markdown: Optional[str] = ""
    meta_description: str = ""
    faq_schema: str = ""

    def has_body(self) -> bool:
        return bool(self.body_markdown and self.body_markdown.strip())

    def title_or_fallback(self, fallback: str) -> str:
        if self.title and self.title.strip():
            return self.title
        return fallback
