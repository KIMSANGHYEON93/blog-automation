"""네이버 SmartEditor ONE 조작 — SeleniumBase `sb` 인스턴스를 받는다.

참고한 구현(MIT):
- 0x8905/naver-blog-automation `nblog/publisher.py`: 로그인은 사람이, 자동화는 저장된 프로필로
- jjlabsio/md-to-naver-blog: 본문은 text/html 붙여넣기로 넣는다
- choigpt-ai/naver-blog-automation `automation/editor.py`: iframe·팝업 처리

한 글자씩 타이핑하지 않고 붙여넣기 이벤트 한 번으로 본문을 넣는다. 붙여넣기가 먹혔는지는
에디터 컴포넌트 수로 확인하고, 안 먹혔으면 예외를 던진다(조용히 빈 글을 발행하지 않는다).
"""
from __future__ import annotations

import logging
import time

from src.infrastructure.browser.naver import selectors as sel
from src.infrastructure.browser.naver.content import BLOG_HOST, parse_log_no

logger = logging.getLogger(__name__)

EDITOR_TIMEOUT = 20
PUBLISH_URL_TIMEOUT = 30

# 합성 paste 이벤트. SmartEditor는 clipboardData의 text/html을 읽어 컴포넌트로 바꾼다.
_PASTE_JS = """
const [html, text] = arguments;
const target = document.activeElement || document.body;
const data = new DataTransfer();
data.setData('text/html', html);
data.setData('text/plain', text);
target.dispatchEvent(new ClipboardEvent('paste', {
  clipboardData: data, bubbles: true, cancelable: true,
}));
"""

_COUNT_JS = "return document.querySelectorAll(arguments[0]).length;"


class NaverEditorError(RuntimeError):
    pass


def write_url(blog_id: str) -> str:
    return BLOG_HOST + sel.WRITE_PATH.format(blog_id=blog_id)


def is_logged_in(sb, blog_id: str) -> bool:
    """글쓰기 화면이 로그인 페이지로 튕기지 않으면 세션이 살아 있다."""
    sb.open(write_url(blog_id))
    time.sleep(3)
    return "nid.naver.com" not in sb.get_current_url()


def open_editor(sb, blog_id: str) -> None:
    if not is_logged_in(sb, blog_id):
        raise NaverEditorError("네이버 세션 없음 — scripts/naver_blog.py login 으로 먼저 로그인")
    _enter_editor_frame(sb)
    if not _first_visible(sb, sel.EDITOR_READY, timeout=EDITOR_TIMEOUT):
        raise NaverEditorError("SmartEditor 로딩 실패 — selectors.EDITOR_READY 확인")
    _dismiss_popups(sb)


def fill_title(sb, title: str) -> None:
    target = _first_visible(sb, sel.TITLE)
    if not target:
        raise NaverEditorError("제목 입력란을 찾지 못함 — selectors.TITLE 확인")
    sb.click(target)
    sb.driver.switch_to.active_element.send_keys(title)
    time.sleep(0.5)


def paste_body(sb, html: str, plain_text: str) -> None:
    target = _first_visible(sb, sel.BODY)
    if not target:
        raise NaverEditorError("본문 입력란을 찾지 못함 — selectors.BODY 확인")
    before = sb.execute_script(_COUNT_JS, sel.BODY_COMPONENTS)
    sb.click(target)
    sb.execute_script(_PASTE_JS, html, plain_text)
    time.sleep(2)
    after = sb.execute_script(_COUNT_JS, sel.BODY_COMPONENTS)
    if after <= before:
        raise NaverEditorError(
            f"본문 붙여넣기가 반영되지 않음 (컴포넌트 {before} → {after})"
        )
    logger.info(f"본문 붙여넣기 완료: 컴포넌트 {before} → {after}")


def save_draft(sb) -> None:
    _click_first(sb, sel.SAVE_DRAFT, "임시저장 버튼")
    time.sleep(2)


def publish(sb, tags: list[str]) -> str:
    """발행 레이어를 열어 태그를 넣고 확정한다. 발행된 글 URL을 반환."""
    _click_first(sb, sel.PUBLISH_OPEN, "발행 버튼")
    time.sleep(1.5)
    if tags:
        _fill_tags(sb, tags)
    _click_first(sb, sel.PUBLISH_CONFIRM, "발행 확인 버튼")
    return _wait_published_url(sb)


def _enter_editor_frame(sb) -> None:
    sb.switch_to_default_content()
    if sb.is_element_present(sel.MAIN_FRAME):
        sb.switch_to_frame(sel.MAIN_FRAME)


def _dismiss_popups(sb) -> None:
    for selector in sel.POPUP_CLOSE:
        if sb.is_element_visible(selector):
            try:
                sb.click(selector)
                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"팝업 닫기 실패(무시): {selector} — {e}")


def _fill_tags(sb, tags: list[str]) -> None:
    target = _first_visible(sb, sel.TAG_INPUT, timeout=5)
    if not target:
        # 태그는 발행을 막을 이유가 아니다. 경고만 남긴다.
        logger.warning("태그 입력란을 찾지 못해 태그 없이 발행 — selectors.TAG_INPUT 확인")
        return
    for tag in tags:
        sb.type(target, tag + "\n")
        time.sleep(0.3)


def _wait_published_url(sb) -> str:
    deadline = time.time() + PUBLISH_URL_TIMEOUT
    while time.time() < deadline:
        sb.switch_to_default_content()
        url = str(sb.get_current_url())
        if parse_log_no(url):
            return url
        time.sleep(1)
    raise NaverEditorError(f"발행 후 글 URL을 확인하지 못함 (현재: {sb.get_current_url()})")


def _first_visible(sb, selectors: list[str], timeout: float = 0) -> str | None:
    deadline = time.time() + timeout
    while True:
        for selector in selectors:
            if sb.is_element_visible(selector):
                return selector
        if time.time() >= deadline:
            return None
        time.sleep(0.5)


def _click_first(sb, selectors: list[str], label: str) -> None:
    target = _first_visible(sb, selectors, timeout=5)
    if not target:
        raise NaverEditorError(f"{label}을(를) 찾지 못함 — selectors 확인")
    sb.click(target)
