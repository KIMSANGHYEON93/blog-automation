"""ThumbnailService — Domain service for thumbnail image extraction."""
from __future__ import annotations

import re


class ThumbnailService:
    """HTML 본문에서 대표이미지 URL을 추출하는 도메인 서비스."""

    @staticmethod
    def extract_first_image_url(html: str) -> str:
        """HTML 본문에서 첫 번째 <img> src URL 추출 (대표이미지 자동 선택용).

        - data: URI, 상대 경로는 건너뜀
        - http/https URL만 반환, 없으면 빈 문자열
        """
        if not html:
            return ""
        for match in re.finditer(r'<img\s[^>]*?src=["\']([^"\']+)["\']', html):
            src = match.group(1).strip()
            if src.startswith("data:"):
                continue
            if not src.startswith(("http://", "https://")):
                continue
            return src
        return ""
