"""네이버 사진 — 업로드 전 재인코딩."""
import io

from PIL import Image

from src.infrastructure.browser.naver.images import image_prompt, reencode_jpeg


def _jpeg_with_exif() -> bytes:
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x010F] = "black-forest-labs/flux.1-schnell"  # Make — Pollinations 원본에 있는 태그
    Image.new("RGB", (32, 18), (240, 200, 180)).save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_EXIF를_뺀_일반_JPEG로_다시_저장한다():
    # 2026-09-24 실측: Pollinations 원본 일부는 네이버가 '파일 전송 오류'로 거부, 재저장하면 통과
    original = _jpeg_with_exif()
    assert b"Exif" in original[:40]
    out = reencode_jpeg(original)
    assert out is not None
    assert out[:3] == b"\xff\xd8\xff"
    assert b"Exif" not in out[:40]
    assert Image.open(io.BytesIO(out)).size == (32, 18)


def test_이미지가_아니면_None():
    assert reencode_jpeg(b"not an image") is None


def test_사진_설명은_글자를_금지하고_주제를_담는다():
    prompt = image_prompt("MCP란", "어떻게 작동하나요")
    assert "no text" in prompt
    assert "MCP란 - 어떻게 작동하나요" in prompt
