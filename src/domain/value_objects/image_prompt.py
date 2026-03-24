"""ImagePrompt — Value Object for AI image generation prompt."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImagePrompt:
    """AI 이미지 생성에 사용할 프롬프트 정보."""
    prompt: str
    style: str = "digital-art"
    size: str = "1024x1024"
    quality: str = "standard"

    def is_valid(self) -> bool:
        """프롬프트가 유효한지 확인."""
        return bool(self.prompt and self.prompt.strip())
