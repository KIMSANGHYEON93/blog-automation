"""CategorySyncAdapter — Tistory 카테고리 Selenium 어댑터."""
from __future__ import annotations

import json
import logging

from src.domain.ports.category_sync_port import CategorySyncPort, RemoteCategory

logger = logging.getLogger(__name__)


class SeleniumCategorySyncAdapter(CategorySyncPort):
    """Tistory /manage/category.json 엔드포인트에서 카테고리 목록 가져오기."""

    def __init__(self, sb, blog_name: str):
        self._sb = sb
        self._blog_name = blog_name

    def fetch_categories(self) -> list[RemoteCategory]:
        """Selenium으로 Tistory 카테고리 JSON 페이지 접근 후 파싱."""
        url = f"https://{self._blog_name}.tistory.com/manage/category.json"
        logger.info(f"카테고리 동기화: {url}")

        self._sb.open(url)
        page_source = self._sb.get_page_source()

        # JSON 응답 파싱 (페이지 소스에서 body 텍스트 추출)
        try:
            # 브라우저가 JSON을 pre 태그로 감싸는 경우
            text = page_source
            if "<pre>" in text:
                start = text.index("<pre>") + 5
                end = text.index("</pre>")
                text = text[start:end]
            elif "<body>" in text:
                start = text.index("<body>") + 6
                end = text.index("</body>")
                text = text[start:end].strip()

            data = json.loads(text)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"카테고리 JSON 파싱 실패: {e}")
            return []

        return self._parse_categories(data)

    @staticmethod
    def _parse_categories(data: dict) -> list[RemoteCategory]:
        """Tistory 카테고리 JSON 응답 파싱."""
        results: list[RemoteCategory] = []
        categories = data.get("categories", [])

        for cat in categories:
            name = cat.get("label", cat.get("name", ""))
            cat_id = str(cat.get("id", ""))
            parent = cat.get("parent", "")
            count = int(cat.get("entryCount", cat.get("entries", 0)))

            if name and cat_id:
                results.append(RemoteCategory(
                    name=name,
                    category_id=cat_id,
                    parent=str(parent) if parent else "",
                    entry_count=count,
                ))

        logger.info(f"원격 카테고리 {len(results)}개 발견")
        return results
