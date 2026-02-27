"""TistoryEditor — Tistory blog editor automation."""
import logging
import time

from src.domain.entities.post import Post
from src.domain.value_objects.publish_result import PublishResult
from src.infrastructure.browser.dom_selectors import (
    find_element,
    MARKDOWN_MODE_SELECTORS,
    TITLE_SELECTORS,
    CONTENT_AREA_SELECTORS,
    SAVE_BUTTON_SELECTORS,
)
from src.infrastructure.browser.js_injector import safe_js_inject

logger = logging.getLogger(__name__)


def publish_post(sb, post: Post, blog_name: str) -> PublishResult:
    """티스토리 에디터에 포스트 발행. PublishResult 반환."""
    try:
        write_url = f"https://{blog_name}.tistory.com/manage/post/write"
        sb.open(write_url)
        time.sleep(2)

        # 제목 입력
        title_sel = find_element(sb, TITLE_SELECTORS)
        if not title_sel:
            return PublishResult.fail("제목 입력창을 찾을 수 없음")
        sb.triple_click(title_sel)
        sb.type(title_sel, post.content.title_or_fallback(post.keyword))
        time.sleep(0.5)

        # 마크다운 모드 전환
        md_sel = find_element(sb, MARKDOWN_MODE_SELECTORS)
        if md_sel:
            sb.click(md_sel)
            time.sleep(1)

        # 본문 주입 (JS)
        content_sel = find_element(sb, CONTENT_AREA_SELECTORS) or ".CodeMirror"
        success = safe_js_inject(sb, content_sel, post.content.body_markdown)
        if not success:
            # Fallback: 직접 타이핑
            sb.click(content_sel)
            sb.type(content_sel, post.content.body_markdown)
        time.sleep(1)

        # 임시저장 또는 발행
        save_sel = find_element(sb, SAVE_BUTTON_SELECTORS)
        if save_sel:
            sb.click(save_sel)
            time.sleep(2)

        current_url = sb.get_current_url()
        logger.info(f"발행 완료: {post.keyword} → {current_url}")
        return PublishResult.ok(current_url)

    except Exception as e:
        logger.error(f"발행 실패: {post.keyword} — {e}")
        return PublishResult.fail(str(e))
