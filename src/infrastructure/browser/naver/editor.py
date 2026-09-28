"""네이버 SmartEditor ONE 조작 — SeleniumBase `sb` 인스턴스를 받는다.

참고한 구현(MIT):
- 0x8905/naver-blog-automation `nblog/publisher.py`: 로그인은 사람이, 자동화는 저장된 프로필로
- jjlabsio/md-to-naver-blog: 본문은 text/html 붙여넣기로 넣는다
- choigpt-ai/naver-blog-automation `automation/editor.py`: iframe·팝업 처리

한 글자씩 타이핑하지 않고 붙여넣기 이벤트 한 번으로 본문을 넣는다. 붙여넣기가 먹혔는지는
에디터 컴포넌트 수로 확인하고, 안 먹혔으면 예외를 던진다(조용히 빈 글을 발행하지 않는다).
"""
from __future__ import annotations

import base64
import logging
import time

from src.infrastructure.browser.naver import selectors as sel
from src.infrastructure.browser.naver.content import BLOG_HOST, parse_blog_id, parse_log_no

logger = logging.getLogger(__name__)

EDITOR_TIMEOUT = 20
PUBLISH_URL_TIMEOUT = 30

# 발행 확인을 누른 뒤 URL을 못 받으면 실제로는 발행됐을 수 있다 — 재시도하면 중복 발행
PUBLISH_UNCONFIRMED = "발행 여부 수동 확인 필요"

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
_TEXT_LEN_JS = (
    "return [...document.querySelectorAll(arguments[0])]"
    ".reduce((n, p) => n + p.innerText.trim().length, 0);"
)

# 이미지 파일 paste — 에디터가 네이버 서버에 올리고 사진 컴포넌트를 만든다.
_PASTE_FILE_JS = """
const [b64, name] = arguments;
const bin = atob(b64);
const bytes = new Uint8Array(bin.length);
for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
const data = new DataTransfer();
data.items.add(new File([bytes], name, {type: 'image/jpeg'}));
const target = document.activeElement || document.body;
target.dispatchEvent(new ClipboardEvent('paste', {
  clipboardData: data, bubbles: true, cancelable: true,
}));
"""

IMAGE_UPLOAD_TIMEOUT = 45

# 모바일 공개 글의 점검 수치(2026-09-24~26 실측한 DOM). 태그는 6개만 보이고 나머지는 '+N' 버튼
_POST_STATS_JS = """
const body = document.querySelector('.se-main-container');
const shown = document.querySelectorAll('[class*="PostTag__tag"]').length;
const more = [...document.querySelectorAll('[class*="PostTag"] button, [class*="PostTag"] a')]
  .map(e => (e.innerText || '').trim()).find(t => /^\\+\\d+$/.test(t));
const category = document.querySelector('.blog_category, [class*="category"] a');
return {
  category: category ? category.innerText.trim() : '',
  tags: shown + (more ? parseInt(more.slice(1), 10) : 0),
  images: body ? body.querySelectorAll('.se-image img').length : 0,
  quotes: body ? body.querySelectorAll('.se-quotation').length : 0,
  orphan_numbers: body ? [...body.querySelectorAll('.se-text-paragraph')]
    .filter(p => /^\\d+\\.$/.test(p.innerText.trim())).length : 0,
};
"""


class NaverEditorError(RuntimeError):
    pass


def write_url(blog_id: str) -> str:
    return BLOG_HOST + sel.WRITE_PATH.format(blog_id=blog_id)


def is_logged_in(sb, blog_id: str) -> bool:
    """MyBlog.naver 가 로그인 페이지로 튕기지 않으면 세션이 살아 있다.

    글쓰기 화면으로 확인하면 open_editor()가 같은 화면을 다시 열 때 '페이지를 떠나시겠습니까'
    확인창이 떠 이후 명령이 막힌다(2026-09-23 실측). 그래서 가벼운 페이지로 확인한다.
    """
    _open(sb, f"{BLOG_HOST}/MyBlog.naver")
    time.sleep(3)
    current = str(sb.get_current_url())
    if "nid.naver.com" in current:
        return False
    actual = parse_blog_id(current)
    if actual and actual != blog_id:
        # 로그인 아이디를 블로그 아이디로 넣으면 글쓰기 iframe이 안 열려 원인을 알기 어렵다
        raise NaverEditorError(
            f"NAVER_BLOG_ID가 실제 블로그 주소와 다름: 설정 {blog_id!r} / 실제 {actual!r}"
            f" — .env 의 NAVER_BLOG_ID={actual} 로 바꾸세요"
        )
    return True


def open_editor(sb, blog_id: str) -> None:
    _open(sb, write_url(blog_id))
    time.sleep(3)
    if "nid.naver.com" in sb.get_current_url():
        raise NaverEditorError("네이버 세션 없음 — scripts/naver_blog.py login 으로 먼저 로그인")
    _enter_editor_frame(sb)
    time.sleep(2)
    _dismiss_draft_confirm(sb)  # 에디터 로딩 뒤에 뜨는 경우도 있다
    if not _first_visible(sb, sel.EDITOR_READY, timeout=EDITOR_TIMEOUT):
        raise NaverEditorError("SmartEditor 로딩 실패 — selectors.EDITOR_READY 확인")
    _dismiss_popups(sb)


def fill_title(sb, title: str) -> None:
    from selenium.webdriver.common.action_chains import ActionChains

    target = _first_visible(sb, sel.TITLE)
    if not target:
        raise NaverEditorError("제목 입력란을 찾지 못함 — selectors.TITLE 확인")
    sb.click(target)
    time.sleep(0.5)
    # 포커스가 숨은 input_buffer iframe에 있으므로 요소가 아니라 키 입력으로 보낸다
    ActionChains(sb.driver).send_keys(title).perform()
    time.sleep(0.5)
    typed = sb.execute_script(f"return document.querySelector({target!r})?.innerText || ''")
    if title.strip() not in str(typed):
        raise NaverEditorError(f"제목 입력이 반영되지 않음 (현재: {str(typed)[:40]!r})")


def paste_body(sb, html: str, plain_text: str) -> None:
    focus_body(sb)
    paste_html(sb, html, plain_text)


def focus_body(sb) -> None:
    """본문 입력란에 커서를 둔다. 이후 붙여넣기는 커서 뒤에 이어진다(다시 클릭하면 위치가 바뀜)."""
    target = _first_visible(sb, sel.BODY)
    if not target:
        raise NaverEditorError("본문 입력란을 찾지 못함 — selectors.BODY 확인")
    sb.click(target)
    time.sleep(0.5)


def paste_image(sb, data: bytes) -> bool:
    """이미지 파일을 커서 위치에 붙여넣는다. 네이버가 자기 서버에 올린다(2026-09-24 실측).

    HTML의 <img>(외부 URL·data URI)는 에디터가 버린다 — 파일로 붙여넣어야 한다.
    실패해도 발행을 막지 않도록 예외 대신 False를 돌려준다.
    """
    before = sb.execute_script(_COUNT_JS, sel.UPLOADED_IMAGES)
    name = f"image_{int(time.time() * 1000)}.jpg"
    _dispatch_in_input_buffer(sb, _PASTE_FILE_JS, base64.b64encode(data).decode(), name)
    started = time.time()
    while time.time() - started < IMAGE_UPLOAD_TIMEOUT:
        time.sleep(1)
        if sb.execute_script(_COUNT_JS, sel.UPLOADED_IMAGES) > before:
            logger.info(f"사진 업로드 완료 ({time.time() - started:.0f}초)")
            return True
        error_button = _first_visible(sb, sel.UPLOAD_ERROR_CLOSE)
        if error_button:
            logger.warning("사진 '파일 전송 오류' — 사진 없이 계속")
            sb.click(error_button)
            time.sleep(1)
            return False
    logger.warning(f"사진 업로드가 {IMAGE_UPLOAD_TIMEOUT}초 안에 끝나지 않음 — 사진 없이 계속")
    return False


def paste_html(sb, html: str, plain_text: str) -> None:
    # 문단 수가 아니라 글자 수 변화로 판정: 빈 문단에 한 줄을 붙이면 문단 수가 그대로고,
    # 빈 본문의 안내 문구('글감과 함께…')가 글자 수에 잡혔다가 사라져 줄 수도 있다(2026-09-24 실측)
    before = sb.execute_script(_TEXT_LEN_JS, sel.BODY_PARAGRAPHS)
    _dispatch_paste_in_input_buffer(sb, html, plain_text)
    time.sleep(2)
    after = sb.execute_script(_TEXT_LEN_JS, sel.BODY_PARAGRAPHS)
    if after == before:
        raise NaverEditorError(
            f"본문 붙여넣기가 반영되지 않음 (글자 {before} → {after})"
        )
    logger.info(f"본문 붙여넣기 완료: 글자 {before} → {after}")


def save_draft(sb) -> None:
    _click_first(sb, sel.SAVE_DRAFT, "임시저장 버튼")
    time.sleep(2)


def publish(sb, tags: list[str], category: str = "") -> str:
    """발행 레이어를 열어 카테고리·태그를 넣고 확정한다. 발행된 글 URL을 반환."""
    _click_first(sb, sel.PUBLISH_OPEN, "발행 버튼")
    time.sleep(1.5)
    if category:
        _select_category(sb, category)
    if tags:
        _fill_tags(sb, tags)
    _click_first(sb, sel.PUBLISH_CONFIRM, "발행 확인 버튼")
    try:
        return _wait_published_url(sb)
    except NaverEditorError:
        raise
    except Exception as e:
        # 확인을 누른 뒤라 실제로 발행됐을 수 있다 — 재발행하지 않게 표식을 남긴다
        raise NaverEditorError(f"발행 확인 뒤 오류({e}) — {PUBLISH_UNCONFIRMED}") from e


def collect_post_stats(sb, url: str) -> dict:
    """공개 글(모바일 화면)을 열어 점검용 수치를 읽는다. 태그는 '+N' 접힘까지 센다."""
    _open(sb, url.replace("://blog.naver.com", "://m.blog.naver.com"))
    time.sleep(3)
    return dict(sb.execute_script(_POST_STATS_JS))


def _open(sb, url: str) -> None:
    """이동 전에 남은 확인창(beforeunload 등)을 수락한다. 떠 있으면 이후 명령이 전부 막힌다."""
    sb.switch_to_default_content()
    _accept_alert(sb)
    sb.open(url)
    _accept_alert(sb)


def _accept_alert(sb) -> None:
    try:
        sb.driver.switch_to.alert.accept()
        logger.info("브라우저 확인창 수락")
    except Exception:
        pass  # 확인창이 없는 게 정상


def _dispatch_paste_in_input_buffer(sb, html: str, plain_text: str) -> None:
    _dispatch_in_input_buffer(sb, _PASTE_JS, html, plain_text)


def _dispatch_in_input_buffer(sb, script: str, *args) -> None:
    """에디터 바깥 문서에 보낸 paste는 무시된다. 숨은 입력 iframe 안에서 보내야 한다."""
    frames = sb.driver.find_elements("css selector", sel.INPUT_BUFFER_FRAME)
    if not frames:
        raise NaverEditorError("입력 버퍼 iframe을 찾지 못함 — selectors.INPUT_BUFFER_FRAME 확인")
    sb.driver.switch_to.frame(frames[0])
    try:
        sb.execute_script(script, *args)
    finally:
        sb.driver.switch_to.parent_frame()


def _dismiss_draft_confirm(sb) -> None:
    """'작성 중인 글이 있습니다. 이어서 작성하시겠습니까?' 네이티브 확인창은 취소한다.

    SmartEditor 자동 저장본이 있으면 진입 몇 초 뒤에 뜨고, 떠 있는 동안 모든 명령이 막힌다.
    수락하면 예전 글이 불러와져 새 본문이 그 뒤에 붙으므로 반드시 취소(새 글)한다.
    """
    try:
        alert = sb.driver.switch_to.alert
        logger.info(f"확인창 취소: {alert.text[:60]}")
        alert.dismiss()
        time.sleep(1)
    except Exception:
        pass  # 확인창이 없는 게 정상


def _enter_editor_frame(sb) -> None:
    sb.switch_to_default_content()
    deadline = time.time() + EDITOR_TIMEOUT
    while time.time() < deadline:
        _dismiss_draft_confirm(sb)
        if sb.is_element_present(sel.MAIN_FRAME):
            sb.switch_to_frame(sel.MAIN_FRAME)
            return
        time.sleep(1)
    raise NaverEditorError("글쓰기 iframe(#mainFrame)이 열리지 않음")


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
        # sb.type은 입력란을 지운 뒤 쓴다 — 마지막 태그만 남았다(2026-09-23 실측)
        sb.add_text(target, tag + "\n")
        time.sleep(0.3)


def _select_category(sb, name: str) -> bool:
    """카테고리 목록에서 이름이 같은 항목을 고른다. 없으면 기본 카테고리로 두고 경고만 남긴다."""
    button = _first_visible(sb, sel.CATEGORY_BUTTON, timeout=3)
    if not button:
        logger.warning("카테고리 선택 상자를 찾지 못함 — 기본 카테고리로 발행")
        return False
    sb.click(button)
    time.sleep(1)
    option = sel.CATEGORY_OPTION.format(name=name)
    if sb.is_element_visible(option):
        sb.click(option)
        time.sleep(0.5)
        logger.info(f"카테고리 선택: {name}")
        return True
    logger.warning(f"카테고리 '{name}'이(가) 블로그에 없음 — 기본 카테고리로 발행")
    sb.click(button)  # 열린 목록 닫기
    return False


def _wait_published_url(sb) -> str:
    deadline = time.time() + PUBLISH_URL_TIMEOUT
    while time.time() < deadline:
        sb.switch_to_default_content()
        url = str(sb.get_current_url())
        if parse_log_no(url):
            return url
        time.sleep(1)
    raise NaverEditorError(
        f"발행 후 글 URL을 확인하지 못함 — {PUBLISH_UNCONFIRMED} "
        f"(현재: {sb.get_current_url()})"
    )


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
