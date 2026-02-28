"""TistoryEditor — Tistory blog editor automation (2026-02-28 updated)."""
import logging
import time

from src.domain.entities.post import Post
from src.domain.value_objects.publish_result import PublishResult
from src.infrastructure.browser.dom_selectors import (
    CONTENT_AREA_SELECTORS,
    EDITOR_PATH,
    MARKDOWN_MODE_SELECTORS,
    MODE_SWITCH_BUTTON_SELECTORS,
    SAVE_BUTTON_SELECTORS,
    TITLE_SELECTORS,
    find_element,
)

logger = logging.getLogger(__name__)


def publish_post(sb, post: Post, blog_name: str) -> PublishResult:
    """티스토리 에디터에 포스트 발행. PublishResult 반환."""
    try:
        if post.content is None or not post.content.body_markdown:
            return PublishResult.fail("포스트 콘텐츠가 없음")

        content = post.content
        body_markdown: str = content.body_markdown or ""

        # 에디터 페이지 열기
        write_url = f"https://{blog_name}.tistory.com{EDITOR_PATH}"
        sb.open(write_url)
        time.sleep(3)

        # 제목 입력
        title_sel = find_element(sb, TITLE_SELECTORS)
        if not title_sel:
            return PublishResult.fail("제목 입력창을 찾을 수 없음")
        sb.click(title_sel)
        sb.type(title_sel, content.title_or_fallback(post.keyword))
        time.sleep(0.5)

        # 마크다운 모드 전환
        _switch_to_markdown_mode(sb)
        time.sleep(2)

        # 본문 주입 (마크다운 모드의 CodeMirror에 직접 주입)
        if not _inject_markdown_content(sb, body_markdown):
            return PublishResult.fail("본문 주입 실패")
        time.sleep(1)

        # 임시저장 (비공개)
        save_sel = find_element(sb, SAVE_BUTTON_SELECTORS, timeout=5)
        if save_sel:
            sb.click(save_sel)
            time.sleep(3)
            logger.info(f"임시저장 완료: {post.keyword}")
        else:
            logger.warning("임시저장 버튼을 찾을 수 없음 — 저장 건너뜀")

        current_url = sb.get_current_url()
        logger.info(f"발행 완료: {post.keyword} → {current_url}")
        return PublishResult.ok(current_url)

    except Exception as e:
        logger.error(f"발행 실패: {post.keyword} — {e}")
        return PublishResult.fail(str(e))


def _switch_to_markdown_mode(sb) -> None:
    """기본모드 → 마크다운 모드 전환."""
    try:
        # 모드 전환 드롭다운 열기
        mode_btn = find_element(sb, MODE_SWITCH_BUTTON_SELECTORS, timeout=5)
        if not mode_btn:
            logger.warning("모드 전환 버튼 없음 — 기본모드로 진행")
            return

        sb.click(mode_btn)
        time.sleep(1)

        # 마크다운 옵션 선택
        md_sel = find_element(sb, MARKDOWN_MODE_SELECTORS, timeout=3)
        if md_sel:
            sb.click(md_sel)
            time.sleep(2)
            logger.info("마크다운 모드 전환 완료")
        else:
            logger.warning("마크다운 옵션 없음 — 기본모드로 진행")

    except Exception as e:
        logger.warning(f"모드 전환 중 오류 (무시): {e}")


def _inject_markdown_content(sb, markdown_text: str) -> bool:
    """마크다운 모드의 CodeMirror에 본문 주입."""
    # 방법 1: CodeMirror API 사용
    try:
        content_sel = find_element(sb, CONTENT_AREA_SELECTORS, timeout=5)
        if content_sel and "CodeMirror" in content_sel:
            success = sb.execute_script("""
                var cm = document.querySelector('.CodeMirror');
                if (cm && cm.CodeMirror) {
                    cm.CodeMirror.setValue(arguments[0]);
                    return true;
                }
                return false;
            """, markdown_text)
            if success:
                logger.info("CodeMirror API로 본문 주입 성공")
                return True
    except Exception as e:
        logger.debug(f"CodeMirror 주입 실패: {e}")

    # 방법 2: TinyMCE API로 HTML 주입 (마크다운 모드 실패 시 fallback)
    try:
        success = sb.execute_script("""
            if (typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor) {
                var html = '<pre>' + arguments[0].replace(/</g, '&lt;') + '</pre>';
                tinyMCE.activeEditor.setContent(html);
                return true;
            }
            return false;
        """, markdown_text)
        if success:
            logger.info("TinyMCE API로 본문 주입 성공 (fallback)")
            return True
    except Exception as e:
        logger.debug(f"TinyMCE 주입 실패: {e}")

    # 방법 3: textarea 직접 입력 (최후 수단)
    try:
        content_sel = find_element(sb, CONTENT_AREA_SELECTORS, timeout=3)
        if content_sel:
            sb.click(content_sel)
            sb.type(content_sel, markdown_text)
            logger.info("직접 타이핑으로 본문 입력 (fallback)")
            return True
    except Exception as e:
        logger.debug(f"직접 타이핑 실패: {e}")

    return False
