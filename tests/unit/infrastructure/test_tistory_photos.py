"""티스토리 사진 표시 — [[사진:파일]]을 첨부 업로드 치환자로 바꾸고, 실패하면 줄을 지운다."""
from src.infrastructure.browser.tistory_photos import photo_replacer, replace_photo_markers


def test_치환자는_에디터가_저장하는_형식이다():
    # 2026-10-08 실측: 에디터 원문은 kage@<키>/<파일>|CDM|1.3|{크기·정렬 JSON}
    assert photo_replacer("rpQxx/dJMc/AAAA", "img.png", 1280, 900) == (
        '[##_Image|kage@rpQxx/dJMc/AAAA/img.png|CDM|1.3|'
        '{"originWidth":"1280","originHeight":"900","style":"alignCenter"}_##]'
    )


def test_사진_표시를_업로드_결과로_바꾼다():
    md = "가.\n\n[[사진:a1.jpg]]\n\n출처: https://x.com (캡처 2026-10-08)"
    out = replace_photo_markers(md, lambda name: f"<{name}>")
    assert out == "가.\n\n<a1.jpg>\n\n출처: https://x.com (캡처 2026-10-08)"


def test_업로드에_실패하면_표시_줄을_지운다():
    # 표시 문자가 글에 그대로 노출되면 안 된다
    md = "가.\n\n[[사진:gone.jpg]]\n\n나."
    assert "[[사진" not in replace_photo_markers(md, lambda name: None)
