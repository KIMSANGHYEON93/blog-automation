"""SetThumbnailsUseCase — Generate AI thumbnails and set them on published posts.

기존 ThumbnailUploadPort 방식 대신 BrowserPort.update()를 사용.
update_post()는 Google Sheets 원본 데이터 기반으로 모든 필드를 올바르게 처리:
- 카테고리 ID 자동 해석
- 내부 링크, FAQ 스키마, HTML 최적화
- 썸네일 URL 반영
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.image_generation_port import ImageGenerationPort
from src.domain.ports.post_repository import PostRepository
from src.domain.services.prompt_builder import PromptBuilder
from src.domain.value_objects.thumbnail_result import ThumbnailResult

logger = logging.getLogger(__name__)


@dataclass
class ThumbnailStats:
    total: int = 0
    generated: int = 0
    uploaded: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[ThumbnailResult] = field(default_factory=list)


class SetThumbnailsUseCase:
    def __init__(
        self,
        repo: PostRepository,
        image_gen: ImageGenerationPort,
        browser: BrowserPort,
        max_posts: int = 5,
    ):
        self._repo = repo
        self._image_gen = image_gen
        self._browser = browser
        self._max_posts = max_posts

    def execute(self) -> ThumbnailStats:
        stats = ThumbnailStats()

        published = self._repo.find_published(limit=200)
        # 썸네일 없는 포스트만 필터링
        no_thumbnail = [
            p for p in published
            if p.entry_id
            and (not p.content or not p.content.thumbnail_url)
        ]

        stats.total = len(no_thumbnail)
        if not no_thumbnail:
            logger.info("썸네일 설정 대상 포스트 없음")
            return stats

        targets = no_thumbnail[:self._max_posts]
        logger.info(f"썸네일 생성 대상: {len(targets)}건 (전체 미설정: {stats.total}건)")

        for post in targets:
            title = ""
            if post.content and post.content.title:
                title = post.content.title
            prompt = PromptBuilder.build(
                keyword=post.keyword,
                category=post.category,
                title=title,
            )
            logger.info(f"이미지 생성 시작: row={post.row_index}, keyword={post.keyword}")

            # 1. 이미지 생성
            try:
                image_url = self._image_gen.generate(prompt)
            except Exception as e:
                logger.error(f"이미지 생성 실패: {post.keyword} — {e}")
                result = ThumbnailResult.fail(
                    str(e), row_index=post.row_index, keyword=post.keyword,
                )
                stats.results.append(result)
                stats.failed += 1
                continue

            stats.generated += 1
            logger.info(f"이미지 생성 완료: {post.keyword} → {image_url[:80]}")

            # 2. PostContent에 thumbnail_url 반영 (frozen이므로 replace 사용)
            new_content = replace(post.content, thumbnail_url=image_url)
            post.content = new_content

            # 3. Sheets에 thumbnail_url 저장
            self._repo.save_thumbnail_url(post.row_index, image_url)

            # 4. BrowserPort.update()로 포스트 재발행
            #    update_post()가 모든 필드를 올바르게 처리 (카테고리, 내부링크 등)
            try:
                pub_result = self._browser.update(post)
            except Exception as e:
                logger.error(f"썸네일 반영 실패: {post.keyword} — {e}")
                result = ThumbnailResult.fail(
                    str(e), row_index=post.row_index, keyword=post.keyword,
                )
                stats.results.append(result)
                stats.failed += 1
                continue

            if pub_result.success:
                result = ThumbnailResult.ok(
                    image_url, row_index=post.row_index, keyword=post.keyword,
                )
                stats.results.append(result)
                stats.uploaded += 1
                logger.info(f"썸네일 설정 완료: {post.keyword}")
            else:
                result = ThumbnailResult.fail(
                    pub_result.error or "업데이트 실패",
                    row_index=post.row_index, keyword=post.keyword,
                )
                stats.results.append(result)
                stats.failed += 1

        return stats
