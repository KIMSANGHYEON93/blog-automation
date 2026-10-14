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
# 키 없이 쓰는 무료 주소 — 키 계정이 크레딧 없음(402)이면 여기로 다시 받는다
# (2026-10-08~14 네이버 사진 전부 402, 무료 주소는 정상 응답 실측)
_FREE_URL = "https://image.pollinations.ai/prompt"
_FALLBACK_STATUSES = {401, 402, 403}
_DEFAULT_MODEL = "flux"
_MIN_IMAGE_BYTES = 1024


def fetch_image(
    prompt: str, api_key: str = "", seed: int = 0,
    width: int = 1024, height: int = 576, model: str = _DEFAULT_MODEL,
) -> tuple[bytes, str]:
    """이미지 바이트와 받은 주소. 키 계정이 결제·인증 오류면 무료 주소로 한 번 더.

    실패는 RuntimeError.
    """
    query = f"width={width}&height={height}&seed={seed}&model={model}"
    encoded = urllib.parse.quote(prompt, safe="")
    attempts: list[tuple[str, dict[str, str]]] = []
    if api_key:
        attempts.append((f"{_BASE_URL}/{encoded}?{query}",
                         {"Authorization": f"Bearer {api_key}"}))
    attempts.append((f"{_FREE_URL}/{encoded}?{query}&nologo=true", {}))
    for i, (url, headers) in enumerate(attempts):
        try:
            resp = requests.get(url, headers=headers, timeout=120)
            resp.raise_for_status()
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", 0)
            if i + 1 < len(attempts) and status in _FALLBACK_STATUSES:
                logger.warning(f"Pollinations 키 계정 응답 {status} — 무료 주소로 다시 받습니다")
                continue
            raise RuntimeError(f"Pollinations API 호출 실패: {e}") from e
        except requests.RequestException as e:
            raise RuntimeError(f"Pollinations API 호출 실패: {e}") from e
        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type:
            raise RuntimeError(f"이미지가 아닌 응답: content-type={content_type}")
        if len(resp.content) < _MIN_IMAGE_BYTES:
            raise RuntimeError(f"이미지 크기 비정상: {len(resp.content)} bytes")
        return resp.content, url
    raise RuntimeError("Pollinations 요청 주소 없음")  # 도달 불가 — attempts는 항상 1개 이상


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

        logger.info(f"Pollinations 이미지 생성 요청: model={self._model}, seed={seed}")
        data, image_url = fetch_image(prompt.prompt, self._api_key, seed, model=self._model)
        logger.info(f"Pollinations 이미지 생성 완료: {len(data)} bytes, seed={seed}")
        # 받은 주소를 그대로 쓴다 — 무료 주소로 받았으면 무료 주소(키 주소는 방문자가 못 연다)
        return image_url
