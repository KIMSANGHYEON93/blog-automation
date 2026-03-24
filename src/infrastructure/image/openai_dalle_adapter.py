"""OpenAiDalleAdapter — ImageGenerationPort implementation using DALL-E 3 API."""
from __future__ import annotations

import logging

from src.domain.ports.image_generation_port import ImageGenerationPort
from src.domain.value_objects.image_prompt import ImagePrompt

logger = logging.getLogger(__name__)


class OpenAiDalleAdapter(ImageGenerationPort):
    """OpenAI DALL-E 3 API를 사용한 이미지 생성 어댑터.

    비용: standard 1024x1024 ~$0.04/image
    """

    def __init__(self, api_key: str, model: str = "dall-e-3"):
        self._api_key = api_key
        self._model = model

    def generate(self, prompt: ImagePrompt) -> str:
        """DALL-E API로 이미지 생성. 성공 시 이미지 URL 반환."""
        import openai

        if not prompt.is_valid():
            raise ValueError("유효하지 않은 프롬프트")

        client = openai.OpenAI(api_key=self._api_key)

        logger.info(f"DALL-E 이미지 생성 요청: model={self._model}, size={prompt.size}")
        logger.debug(f"프롬프트: {prompt.prompt[:200]}")

        response = client.images.generate(
            model=self._model,
            prompt=prompt.prompt,
            size=prompt.size,
            quality=prompt.quality,
            n=1,
        )

        image_url = response.data[0].url
        if not image_url:
            raise RuntimeError("DALL-E API에서 이미지 URL을 받지 못함")

        logger.info(f"DALL-E 이미지 생성 완료: {image_url[:80]}")
        return image_url
