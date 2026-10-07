"""티스토리 본문의 사진 표시([[사진:파일]]) — 첨부로 올려 에디터와 같은 치환자로 바꾼다.

업로드 응답 주소는 서명이 붙고 몇 주 뒤 만료된다(서명 없는 주소는 404, 2026-10-08 실측).
그래서 본문에는 주소가 아니라 치환자(kage@키)를 넣는다 — 티스토리가 볼 때마다 새 주소를 만든다.
"""
from __future__ import annotations

import io
import json
import logging
from collections.abc import Callable
from pathlib import Path

import requests  # type: ignore[import-untyped]
from PIL import Image

from src.domain.services.photo_markers import PHOTO_LINE

logger = logging.getLogger(__name__)

# 대시보드가 사진을 저장하는 곳(네이버와 같은 폴더) — 실행 위치와 무관하게 저장소 기준
PHOTO_DIR = Path(__file__).resolve().parents[3] / "uploads" / "naver"
PREVIEW_PLACEHOLDER = "(사진은 발행할 때 올라갑니다)"


def photo_replacer(key: str, filename: str, width: int, height: int) -> str:
    meta = json.dumps({"originWidth": str(width), "originHeight": str(height),
                       "style": "alignCenter"}, separators=(",", ":"))
    return f"[##_Image|kage@{key}/{filename}|CDM|1.3|{meta}_##]"


def replace_photo_markers(markdown: str, photo: Callable[[str], str | None]) -> str:
    """표시 줄을 photo(파일) 결과로 바꾼다. None이면 줄을 지운다 — 표시 문자가 글에 남지 않게."""
    def _sub(match) -> str:  # type: ignore[no-untyped-def]
        replaced = photo(match.group(1))
        if replaced is None:
            logger.warning(f"사진 올리기 실패 — 사진 없이 계속: {match.group(1)}")
            return ""
        return replaced
    return PHOTO_LINE.sub(_sub, markdown)


def make_uploader(cookies: list[dict], blog_name: str,
                  photo_dir: Path = PHOTO_DIR) -> Callable[[str], str | None]:
    """로그인 세션 쿠키로 /manage/post/attach.json에 올리고 치환자를 돌려주는 함수."""
    session = requests.Session()
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path", "/"))
    headers = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest",
               "Referer": f"https://{blog_name}.tistory.com/manage/newpost/"}

    def upload(filename: str) -> str | None:
        path = photo_dir / filename
        if not path.is_file():
            return None
        data = path.read_bytes()
        try:
            resp = session.post(f"https://{blog_name}.tistory.com/manage/post/attach.json",
                                files={"file": (filename, data, "image/jpeg")},
                                headers=headers, timeout=60, allow_redirects=False)
            body = resp.json()
            width, height = Image.open(io.BytesIO(data)).size
            return photo_replacer(body["key"], body["filename"], width, height)
        except Exception as e:
            logger.warning(f"티스토리 첨부 업로드 실패: {filename} ({e})")
            return None

    return upload
