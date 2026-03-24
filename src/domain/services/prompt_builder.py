"""PromptBuilder — Domain service for building AI image generation prompts."""
from __future__ import annotations

from src.domain.value_objects.image_prompt import ImagePrompt

# 카테고리별 시각 스타일 힌트
_CATEGORY_STYLE_MAP: dict[str, str] = {
    "용어": "clean infographic with icons and labels, minimal background",
    "비교": "split-screen comparison layout with two contrasting elements",
    "트러블슈팅": "technical dashboard with warning indicators and diagnostic tools",
    "AI": "futuristic neural network visualization with glowing nodes",
    "Windows": "modern Windows desktop environment with floating UI elements",
    "Linux": "terminal screen with code and penguin mascot elements",
    "가이드": "step-by-step tutorial illustration with numbered arrows",
    "트렌드": "upward trend chart with modern data visualization",
}

_BASE_SUFFIX = (
    "professional blog thumbnail, clean composition, "
    "vibrant colors, no text overlay, 16:9 aspect ratio feel"
)


class PromptBuilder:
    """키워드와 카테고리로 이미지 생성 프롬프트를 조립하는 도메인 서비스."""

    @staticmethod
    def build(keyword: str, category: str = "", title: str = "") -> ImagePrompt:
        """키워드 + 카테고리를 기반으로 ImagePrompt 생성.

        Args:
            keyword: 포스트 키워드 (핵심 주제)
            category: 카테고리명 (시각 스타일 힌트에 사용)
            title: 포스트 제목 (추가 컨텍스트)

        Returns:
            ImagePrompt with assembled prompt string.
        """
        subject = title if title else keyword

        style_hint = _CATEGORY_STYLE_MAP.get(category, "")
        if not style_hint:
            style_hint = "modern tech illustration with abstract elements"

        prompt = f"{subject}, {style_hint}, {_BASE_SUFFIX}"
        return ImagePrompt(prompt=prompt)
