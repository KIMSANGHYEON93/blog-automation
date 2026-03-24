"""ImageGenerationPort — Domain interface for AI image generation."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.value_objects.image_prompt import ImagePrompt


class ImageGenerationPort(ABC):
    @abstractmethod
    def generate(self, prompt: ImagePrompt) -> str:
        """이미지 생성. 성공 시 이미지 URL 반환, 실패 시 예외 발생."""
        ...
