"""네이버 사진 — 업로드 전 재인코딩."""
import io

from PIL import Image

from src.infrastructure.browser.naver.images import image_prompt, reencode_jpeg, save_photo


def test_직접_올린_사진은_회전을_반영하고_EXIF를_빼서_저장한다(tmp_path):
    # 폰 사진은 EXIF에 위치(GPS)가 있을 수 있고, 회전 정보를 버리면 옆으로 누운 채 올라간다
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: 시계 방향 90도
    Image.new("RGB", (40, 20), (10, 20, 30)).save(buf, "JPEG", exif=exif)
    name = save_photo(buf.getvalue(), tmp_path)
    saved = (tmp_path / name).read_bytes()
    assert b"Exif" not in saved[:40]
    assert Image.open(io.BytesIO(saved)).size == (20, 40)


def test_이미지가_아니면_저장하지_않는다(tmp_path):
    assert save_photo(b"not an image", tmp_path) is None
    assert list(tmp_path.iterdir()) == []


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


def _fits(limit):
    return lambda line: len(line) <= limit


def test_제목은_너비에_맞춰_줄바꿈한다():
    from src.infrastructure.browser.naver.images import wrap_title

    assert wrap_title("감마 AI PPT 만들기 초보자도 10분 만에 끝내는 가이드", _fits(14)) == [
        "감마 AI PPT 만들기", "초보자도 10분 만에", "끝내는 가이드",
    ]


def test_콜론_뒤에서_먼저_줄을_바꾼다():
    from src.infrastructure.browser.naver.images import wrap_title

    assert wrap_title("노션 AI 사용법: 업무 효율 높이는 가이드", _fits(30)) == [
        "노션 AI 사용법:", "업무 효율 높이는 가이드",
    ]


def test_세_줄을_넘으면_None():
    from src.infrastructure.browser.naver.images import wrap_title

    assert wrap_title("가나 다라 마바 사아 자차 카타", _fits(4)) is None  # 한 단어씩 6줄


def test_썸네일은_같은_크기의_JPEG이고_배경과_다르다():
    from src.infrastructure.browser.naver.images import title_thumbnail

    background = _jpeg_with_exif()
    out = title_thumbnail("MCP란 무엇일까요? AI 연동 표준 쉬운 정리", background, keyword="MCP란")
    image = Image.open(io.BytesIO(out))
    assert image.format == "JPEG" and image.size == (32, 18)
    assert out != reencode_jpeg(background)


def test_글꼴이_없으면_배경을_그대로_쓴다(tmp_path):
    from src.infrastructure.browser.naver.images import title_thumbnail

    background = reencode_jpeg(_jpeg_with_exif())
    assert title_thumbnail("제목", background, font_path=str(tmp_path / "없음.ttc")) == background


def test_대표_사진_설명은_꽉_찬_장면을_요구한다():
    # 본문용 'minimal' 스타일은 표지로 쓰면 빈 배경에 의자 하나 같은 그림이 나왔다(2026-09-28)
    prompt = image_prompt("감마 AI PPT 만들기", cover=True)
    assert "full frame" in prompt and "no text" in prompt and "minimal" not in prompt


def test_사진_설명은_글자를_금지하고_주제를_담는다():
    prompt = image_prompt("MCP란", "어떻게 작동하나요")
    assert "no text" in prompt
    assert "MCP란 - 어떻게 작동하나요" in prompt
