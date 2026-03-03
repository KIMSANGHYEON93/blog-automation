"""PostContent — Value Object for blog post content."""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class PostContent:
    title: str | None = ""
    body_markdown: str | None = ""
    meta_description: str = ""
    faq_schema: str = ""
    tags: str = ""
    thumbnail_url: str = ""
    internal_link_keywords: str = ""

    def has_body(self) -> bool:
        return bool(self.body_markdown and self.body_markdown.strip())

    def title_or_fallback(self, fallback: str) -> str:
        if self.title and self.title.strip():
            return self.title
        return fallback

    def internal_keyword_list(self) -> list[str]:
        """내부 링크 키워드 JSON 문자열을 리스트로 반환."""
        if not self.internal_link_keywords:
            return []
        try:
            parsed = json.loads(self.internal_link_keywords)
            if isinstance(parsed, list):
                return [str(k).strip() for k in parsed if str(k).strip()]
            return []
        except (json.JSONDecodeError, TypeError):
            return [
                k.strip()
                for k in self.internal_link_keywords.split(",")
                if k.strip()
            ]

    def tag_list(self) -> list[str]:
        """태그 문자열을 리스트로 반환 (쉼표 구분)."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def faq_ld_json(self) -> str:
        """FAQ 스키마를 LD+JSON 형식으로 반환. 파싱 실패 시 빈 문자열."""
        if not self.faq_schema:
            return ""
        try:
            faq_list = (
                json.loads(self.faq_schema)
                if isinstance(self.faq_schema, str)
                else self.faq_schema
            )
            if not isinstance(faq_list, list) or len(faq_list) == 0:
                return ""
            main_entity = []
            for faq in faq_list:
                if not isinstance(faq, dict) or "question" not in faq or "answer" not in faq:
                    continue
                main_entity.append({
                    "@type": "Question",
                    "name": faq["question"],
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": faq["answer"]
                    }
                })
            if not main_entity:
                return ""
            schema = {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": main_entity
            }
            return json.dumps(schema, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, TypeError, KeyError):
            return ""
