"""PollinationsAdapter — ImageGenerationPort implementation using Pollinations.ai (free)."""
from __future__ import annotations

import hashlib
import logging
import urllib.parse

import requests

from src.domain.ports.image_generation_port import ImageGenerationPort
from src.domain.value_objects.image_prompt import ImagePrompt

logger = logging.getLogger(__name__)

_BASE_URL = "https://gen.pollinations.ai/image"
_DEFAULT_MODEL = "flux"


class PollinationsAdapter(ImageGenerationPort):
    """Pollinations.ai API를 사용한 이미지 생성 어댑터.

    비용: 무료 (enter.pollinations.ai 가입 필요)
    무료 계정: 0.01 pollen/hr, 이미지 1장 = 0.001 pollen → 하루 ~240장
    """

    def __init__(self, api_key: str = "", model: str = _DEFAULT_MODEL):
        self._api_key = api_key
        self._model = model

    def generate(self, prompt: ImagePrompt) -> str:
        """Pollinations API로 이미지 생성. 성공 시 이미지 URL 반환."""
        if not prompt.is_valid():
            raise ValueError("유효하지 않은 프롬프트")

        # 프롬프트 기반 deterministic seed (같은 프롬프트 → 같은 이미지)
        # API seed 범위: 0 ~ 2,147,483,647 (int32 max)
        seed = int(hashlib.md5(prompt.prompt.encode()).hexdigest()[:8], 16) & 0x7FFFFFFF

        # URL 구성
        encoded_prompt = urllib.parse.quote(prompt.prompt, safe="")
        width, height = 1024, 576  # 16:9 블로그 썸네일
        image_url = (
            f"{_BASE_URL}/{encoded_prompt}"
            f"?width={width}&height={height}&seed={seed}&model={self._model}"
        )

        logger.info(f"Pollinations 이미지 생성 요청: model={self._model}, seed={seed}")
        logger.debug(f"URL: {image_url[:200]}")

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            resp = requests.get(image_url, headers=headers, timeout=120)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type:
                raise RuntimeError(
                    f"이미지가 아닌 응답: content-type={content_type}"
                )

            content_length = len(resp.content)
            if content_length < 1024:
                raise RuntimeError(f"이미지 크기 비정상: {content_length} bytes")

            logger.info(
                f"Pollinations 이미지 생성 완료: {content_length} bytes, "
                f"seed={seed}"
            )
            # URL 자체가 영구 접근 가능한 이미지 URL로 사용
            return image_url

        except requests.RequestException as e:
            raise RuntimeError(f"Pollinations API 호출 실패: {e}") from e
