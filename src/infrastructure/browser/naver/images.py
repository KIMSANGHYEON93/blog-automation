"""네이버 글 사진 — 프롬프트를 만들고 Pollinations에서 이미지 파일(바이트)을 받는다.

네이버 에디터는 이미지 URL을 버리고 파일 붙여넣기만 받으므로 URL이 아니라 바이트가 필요하다.
"""
from __future__ import annotations

import hashlib
import io
import logging
import urllib.parse
import uuid
from pathlib import Path
from typing import Callable, Optional

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

ImageFn = Callable[[str], Optional[bytes]]

_BASE_URL = "https://gen.pollinations.ai/image"
# 올린 사진 픽셀 상한(폰 사진 약 1,200만 화소의 3배) — 넘으면 디코딩하지 않는다(압축 폭탄)
MAX_PHOTO_PIXELS = 40_000_000
# macOS 기본 한글 글꼴(ExtraBold=14번 face). 발행은 이 맥에서만 돌아 저장소에 넣지 않는다
THUMBNAIL_FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
THUMBNAIL_FONT_INDEX = 14
_STYLE = "minimal flat illustration, soft pastel colors, clean composition, no text, no letters"
_COVER_STYLE = (
    "vibrant detailed isometric illustration, rich scene filling the full frame, "
    "subject centered, modern tech mood, no empty space, no text, no letters, "
    "no signs, no logos"  # 간판에 가짜 글자가 그려졌다(2026-09-28)
)


def image_prompt(keyword: str, heading: str = "", cover: bool = False) -> str:
    """키워드(+소제목)로 사진 설명을 만든다. 글자가 섞이면 깨진 한글이 나오므로 글자는 금지.

    cover=True(대표 썸네일 배경)는 꽉 찬 장면을 요구한다 — 'minimal' 스타일은 빈 배경이 나온다.
    """
    topic = f"{keyword} - {heading}" if heading else keyword
    style = _COVER_STYLE if cover else _STYLE
    return f"{style}, blog illustration about: {topic}"


def wrap_title(title: str, fits: Callable[[str], bool], max_lines: int = 3) -> list[str] | None:
    """제목을 너비에 맞춰 줄로 나눈다. 콜론 뒤에서 먼저 끊는다. max_lines를 넘으면 None."""
    head, colon, tail = title.partition(":")
    parts = [head + colon, tail] if colon else [title]
    lines: list[str] = []
    for part in parts:
        current = ""
        for word in part.split():
            candidate = f"{current} {word}".strip()
            if fits(candidate) or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    if len(lines) > max_lines or not all(fits(line) for line in lines):
        return None
    return lines


def title_thumbnail(
    title: str, background: bytes, keyword: str = "", brand: str = "",
    font_path: str = THUMBNAIL_FONT, font_index: int = THUMBNAIL_FONT_INDEX,
) -> bytes:
    """대표 썸네일: 왼쪽 짙은 판에 키워드 칩과 제목, 오른쪽에 생성 그림을 선명하게.

    처음엔 그림 전체를 어둡게 깔고 가운데에 제목을 얹었는데, 파스텔 그림이 탁해지고 밋밋했다
    (2026-09-28 실제 제목 3개로 확인). 글꼴이 없으면 배경을 그대로 쓴다.
    """
    try:
        ImageFont.truetype(font_path, 10, index=font_index)
    except OSError:
        logger.warning(f"썸네일 글꼴 없음({font_path}) — 제목 없이 사진만 씀")
        return background
    art = Image.open(io.BytesIO(background)).convert("RGBA")
    width, height = art.size
    canvas = Image.new("RGBA", (width, height), (15, 23, 42, 255))  # 짙은 남색 판

    # 오른쪽 그림: 왼쪽 가장자리를 투명하게 번지게 해 판과 이어 붙인다
    # 생성 그림은 주제가 가운데 있다 — 오른쪽 절반이 아니라 가운데를 잘라 온다
    art_left = int(width * 0.46)
    crop_width = width - art_left
    crop_left = (width - crop_width) // 2
    right = art.crop((crop_left, 0, crop_left + crop_width, height))
    fade = int(crop_width * 0.28)
    mask = Image.new("L", right.size, 255)
    mask_draw = ImageDraw.Draw(mask)
    for x in range(fade):
        # 완만하게 시작하는 곡선 — 직선이면 가운데에 탁한 회색 띠가 생긴다
        mask_draw.line([(x, 0), (x, height)], fill=int(255 * (x / max(1, fade)) ** 2))
    canvas.paste(right, (art_left, 0), mask)

    draw = ImageDraw.Draw(canvas)
    margin = width * 0.065
    max_width = width * 0.56
    size = max(1, int(width * 0.058))
    min_size = max(1, int(width * 0.038))

    def fits(text: str) -> bool:
        return draw.textlength(text, font=font) <= max_width

    while True:
        font = ImageFont.truetype(font_path, size, index=font_index)
        lines = wrap_title(title, fits, max_lines=4)
        if lines or size <= min_size:
            break
        size -= 2
    if not lines:
        # 가장 작은 글씨로도 네 줄을 넘으면 네 번째 줄에서 자른다
        lines = (wrap_title(title, fits, max_lines=99) or [title])[:4]
        lines[-1] = lines[-1].rstrip() + "…"

    line_height = size * 1.28
    chip_font = ImageFont.truetype(font_path, max(1, int(size * 0.46)), index=6)
    chip_height = chip_font.size * 1.9 if keyword else 0
    block = chip_height + (size * 0.6 if keyword else 0) + line_height * len(lines)
    y = (height - block) / 2
    if keyword:
        pad = chip_font.size * 0.9
        chip_width = draw.textlength(keyword, font=chip_font) + pad * 2
        draw.rounded_rectangle(
            [margin, y, margin + chip_width, y + chip_height],
            radius=chip_height / 2, fill=(3, 199, 90, 255),  # 네이버 초록
        )
        draw.text((margin + pad, y + chip_height / 2), keyword, font=chip_font,
                  fill=(255, 255, 255, 255), anchor="lm")
        y += chip_height + size * 0.6
    for line in lines:
        draw.text((margin, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height
    if brand:
        small = ImageFont.truetype(font_path, max(1, int(width * 0.02)), index=2)
        draw.text((margin, height - margin * 0.8), brand, font=small,
                  fill=(148, 163, 184, 255), anchor="ls")

    out = io.BytesIO()
    canvas.convert("RGB").save(out, "JPEG", quality=92)
    return out.getvalue()


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


def save_photo(data: bytes, directory: str | Path) -> str | None:
    """대시보드에서 올린 사진을 저장하고 파일 이름을 돌려준다. 이미지가 아니면 None.

    폰 사진은 EXIF에 위치(GPS)가 있을 수 있어 빼고 저장한다. 회전 정보도 함께 사라지므로
    먼저 픽셀에 반영한다(안 하면 아이폰 사진이 옆으로 누운 채 올라간다).
    """
    try:
        image = Image.open(io.BytesIO(data))
        if image.width * image.height > MAX_PHOTO_PIXELS:
            return None
        upright = ImageOps.exif_transpose(image).convert("RGB")
    except Exception:
        return None
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.jpg"  # 서버가 정한 이름 — 사용자 입력은 경로에 쓰지 않는다
    upright.save(folder / name, "JPEG", quality=90)
    return name


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
