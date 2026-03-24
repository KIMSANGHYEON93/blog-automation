"""ThumbnailUploadPort — Domain interface for uploading thumbnail to blog."""
from __future__ import annotations

from abc import ABC, abstractmethod


class ThumbnailUploadPort(ABC):
    @abstractmethod
    def upload_thumbnail(self, entry_id: str, image_url: str) -> bool:
        """블로그 포스트에 썸네일 업로드/설정.

        Args:
            entry_id: 블로그 포스트 ID
            image_url: 썸네일 이미지 URL

        Returns:
            True if successful.
        """
        ...
