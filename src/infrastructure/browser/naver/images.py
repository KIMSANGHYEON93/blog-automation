"""네이버 글 사진 — 프롬프트를 만들고 Pollinations에서 이미지 파일(바이트)을 받는다.

네이버 에디터는 이미지 URL을 버리고 파일 붙여넣기만 받으므로 URL이 아니라 바이트가 필요하다.
"""
from __future__ import annotations

import hashlib
import io
import logging
import urllib.parse
from typing import Callable, Optional

import requests
from PIL import Image

logger = logging.getLogger(__name__)

ImageFn = Callable[[str], Optional[bytes]]

_BASE_URL = "https://gen.pollinations.ai/image"
_STYLE = "minimal flat illustration, soft pastel colors, clean composition, no text, no letters"


def image_prompt(keyword: str, heading: str = "") -> str:
    """키워드(+소제목)로 사진 설명을 만든다. 글자가 섞이면 깨진 한글이 나오므로 글자는 금지."""
    topic = f"{keyword} - {heading}" if heading else keyword
    return f"{_STYLE}, blog illustration about: {topic}"


def reencode_jpeg(data: bytes) -> bytes | None:
    """EXIF를 뺀 일반 JPEG로 다시 저장한다. 이미지가 아니면 None.

    Pollinations 원본 일부를 네이버가 '파일 전송 오류'로 거부한다 — 같은 그림을 Pillow로
    다시 저장하면 통과한다(2026-09-24 실측, 6장 중 2장이 매번 거부).
    """
    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None
    out = io.BytesIO()
    image.save(out, "JPEG", quality=90)
    return out.getvalue()


def pollinations_image_fn(api_key: str) -> ImageFn:
    def fetch(prompt: str) -> bytes | None:
        seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16) & 0x7FFFFFFF
        url = (f"{_BASE_URL}/{urllib.parse.quote(prompt, safe='')}"
               f"?width=1024&height=576&seed={seed}&model=flux")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            resp = requests.get(url, headers=headers, timeout=120)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"사진 생성 실패 — 사진 없이 계속: {e}")
            return None
        if "image" not in resp.headers.get("content-type", ""):
            logger.warning("사진 생성 응답이 이미지가 아님 — 사진 없이 계속")
            return None
        data = reencode_jpeg(resp.content)
        if data is None:
            logger.warning("사진 생성 응답을 이미지로 읽지 못함 — 사진 없이 계속")
        return data

    return fetch
