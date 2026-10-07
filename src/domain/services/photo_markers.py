"""본문 마크다운 속 사진 표시 — 블로그에는 보이지 않고 발행할 때 사진으로 바뀐다.

- `[[사진:파일.jpg]]`: 대시보드에서 직접 올린 사진(맥의 사진 폴더에 있는 파일)
- `<!-- 사진: 영어 장면 설명 -->`: n8n이 소제목마다 남기는 AI 사진 설명
"""
from __future__ import annotations

import re

# 파일 이름은 점·슬래시 없는 이름 + .jpg — 사진 폴더 밖 경로를 가리킬 수 없다
PHOTO_LINE = re.compile(r"^\[\[사진:([\w-]+\.jpg)\]\][ \t]*$", re.M)
SCENE_COMMENT = re.compile(r"<!--\s*사진:\s*(.*?)\s*-->", re.S)
_FAQ_HEADING = "## 자주 묻는 질문"


def photo_marker(filename: str) -> str:
    return f"[[사진:{filename}]]"


def strip_photo_markers(markdown: str) -> str:
    """길이를 셀 때 쓰는 본문 — 두 표시를 뺀다."""
    return PHOTO_LINE.sub("", SCENE_COMMENT.sub("", markdown))


def insert_photo_marker(markdown: str, filename: str, caption: str = "") -> str:
    """자주 묻는 질문 바로 앞(경험 문단 아래)에 넣고, 없으면 끝에 붙인다.

    caption은 사진 바로 아래 문단(공식 문서 캡처의 출처·날짜).
    """
    marker = photo_marker(filename) + (f"\n\n{caption}" if caption else "")
    at = markdown.find(_FAQ_HEADING)
    if at < 0:
        return f"{markdown.rstrip()}\n\n{marker}"
    return f"{markdown[:at].rstrip()}\n\n{marker}\n\n{markdown[at:]}"
