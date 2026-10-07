"""본문 속 사진 표시 — 직접 올린 사진 [[사진:파일]]과 AI 사진 설명 <!-- 사진: ... -->."""
from src.domain.services.photo_markers import (
    insert_photo_marker,
    photo_marker,
    strip_photo_markers,
)


def test_표시_형식():
    assert photo_marker("a1.jpg") == "[[사진:a1.jpg]]"


def test_길이_셀_때는_두_표시를_뺀다():
    body = "가.\n\n<!-- 사진: a cat at a desk -->\n나.\n\n[[사진:a1.jpg]]\n\n다."
    assert strip_photo_markers(body) == "가.\n\n\n나.\n\n\n\n다."


def test_사진은_자주_묻는_질문_앞에_넣는다():
    body = "본문.\n\n[[직접 해 보니]] 써 보세요.\n\n## 자주 묻는 질문\n\n### Q1"
    assert insert_photo_marker(body, "a1.jpg") == (
        "본문.\n\n[[직접 해 보니]] 써 보세요.\n\n[[사진:a1.jpg]]\n\n## 자주 묻는 질문\n\n### Q1"
    )


def test_자주_묻는_질문이_없으면_끝에_붙인다():
    assert insert_photo_marker("본문.\n", "a1.jpg") == "본문.\n\n[[사진:a1.jpg]]"


def test_사진_아래에_출처_문구를_붙일_수_있다():
    body = "본문.\n\n## 자주 묻는 질문\n\n### Q1"
    assert insert_photo_marker(body, "a1.jpg", caption="출처: https://x.com (캡처 2026-10-08)") == (
        "본문.\n\n[[사진:a1.jpg]]\n\n출처: https://x.com (캡처 2026-10-08)\n\n"
        "## 자주 묻는 질문\n\n### Q1"
    )
