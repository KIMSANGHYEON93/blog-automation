"""네이버 자동 로그인 — 폰에서 세션을 되살리기 위한 대시보드 '네이버 다시 로그인' 전용.

버튼 1회에 제출 1회만 한다. 실패가 반복되면 네이버가 보호조치를 걸기 때문이다.
아이디·비밀번호는 입력란에 값으로만 넣고 로그·메시지·예외에 남기지 않는다.
"""
from __future__ import annotations

import logging
import time
from enum import Enum

from src.infrastructure.browser.naver import selectors as sel

logger = logging.getLogger(__name__)

LOGIN_URL = "https://nid.naver.com/nidlogin.login"


class LoginOutcome(Enum):
    SUCCESS = "success"
    WAITING_APPROVAL = "waiting_approval"
    TIMEOUT = "timeout"
    WRONG_PASSWORD = "wrong_password"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


LOGIN_MESSAGES = {
    LoginOutcome.SUCCESS: "네이버 로그인 성공",
    LoginOutcome.WAITING_APPROVAL: "폰 네이버 앱에서 로그인을 승인하세요",
    LoginOutcome.TIMEOUT: "폰 승인 시간 초과 — 다시 눌러 주세요",
    LoginOutcome.WRONG_PASSWORD: "아이디·비밀번호 확인 필요 (.env의 NAVER_LOGIN_ID·NAVER_LOGIN_PW)",
    LoginOutcome.BLOCKED: "캡차·보호조치 — 맥에서 scripts/naver_blog.py login 으로 직접 로그인",
    LoginOutcome.UNKNOWN: "로그인 결과 불명 — 직접 확인",
}


def classify_login_page(url: str, page_text: str, has_captcha: bool) -> LoginOutcome:
    """제출 뒤 화면 판정. 로그인 페이지(nid)를 벗어났으면 성공으로 본다."""
    if "nid.naver.com" not in url:
        return LoginOutcome.SUCCESS
    if has_captcha or any(m in page_text for m in sel.LOGIN_BLOCKED_MARKERS):
        return LoginOutcome.BLOCKED
    if any(m in page_text for m in sel.LOGIN_WRONG_PASSWORD_MARKERS):
        return LoginOutcome.WRONG_PASSWORD
    if any(m in page_text for m in sel.LOGIN_APPROVAL_MARKERS):
        return LoginOutcome.WAITING_APPROVAL
    return LoginOutcome.UNKNOWN


APPROVAL_TIMEOUT = 300

# 값은 인자로만 넘긴다 — 스크립트 문자열에 넣으면 드라이버 로그에 남을 수 있다
_SET_VALUE_JS = """
const [selector, value] = arguments;
const el = document.querySelector(selector);
if (!el) return false;
el.focus();
el.value = value;
el.dispatchEvent(new Event('input', {bubbles: true}));
el.dispatchEvent(new Event('change', {bubbles: true}));
return true;
"""
_CHECK_KEEP_JS = """
for (const selector of arguments[0]) {
  const el = document.querySelector(selector);
  if (el) { if (!el.checked) el.click(); return true; }
}
return false;
"""
_BODY_TEXT_JS = "return document.body ? document.body.innerText : '';"


def auto_login(sb, login_id: str, login_pw: str, timeout: float = APPROVAL_TIMEOUT,
               poll: float = 2.0, clock=time.monotonic, sleep=time.sleep) -> LoginOutcome:
    """로그인 페이지에 값을 넣고 한 번 제출한 뒤, 폰 승인을 기다리며 결과를 판정한다."""
    sb.open(LOGIN_URL)
    sleep(2)
    # 이미 로그인된 세션: LOGIN_URL에 접속했으나 로그인 페이지를 벗어났으면 성공으로 본다
    if "nid.naver.com" not in str(sb.get_current_url()):
        logger.info("이미 로그인된 세션 — 입력 생략")
        return LoginOutcome.SUCCESS
    for selector, value in ((sel.LOGIN_ID_INPUT, login_id), (sel.LOGIN_PW_INPUT, login_pw)):
        if not sb.execute_script(_SET_VALUE_JS, selector, value):
            logger.error(f"로그인 입력란을 찾지 못함 — selectors 확인: {selector}")
            return LoginOutcome.UNKNOWN
    if not sb.execute_script(_CHECK_KEEP_JS, sel.LOGIN_KEEP):
        logger.warning("'로그인 상태 유지' 체크박스를 찾지 못함 — 세션이 짧게 끝날 수 있음")
    submit = next((s for s in sel.LOGIN_SUBMIT if sb.is_element_visible(s)), None)
    if submit is None:
        logger.error(f"로그인 버튼을 찾지 못함 — selectors 확인: {sel.LOGIN_SUBMIT}")
        return LoginOutcome.UNKNOWN
    sb.click(submit)
    logger.info("네이버 로그인 제출 — 폰 승인 대기")

    deadline = clock() + timeout
    last = LoginOutcome.UNKNOWN
    device_clicked = False
    while True:
        sleep(poll)
        text = str(sb.execute_script(_BODY_TEXT_JS) or "")
        outcome = classify_login_page(
            str(sb.get_current_url()), text, bool(sb.is_element_present(sel.LOGIN_CAPTCHA)),
        )
        if outcome in (LoginOutcome.SUCCESS, LoginOutcome.WRONG_PASSWORD, LoginOutcome.BLOCKED):
            logger.info(f"네이버 로그인 결과: {outcome.value}")
            return outcome
        if (not device_clicked and any(m in text for m in sel.LOGIN_DEVICE_MARKERS)
                and sb.is_element_visible(sel.LOGIN_DEVICE_REGISTER)):
            sb.click(sel.LOGIN_DEVICE_REGISTER)
            device_clicked = True
        # 모르는 화면도 바로 멈추지 않는다 — 네이버 2단계 화면 문구를 다 알 수 없어서,
        # 바로 멈추면 정상 승인 대기를 끊는다. 시간이 다 되면 결과 불명으로 끝낸다
        last = outcome
        if clock() >= deadline:
            final = LoginOutcome.TIMEOUT if last is LoginOutcome.WAITING_APPROVAL else last
            logger.warning(f"네이버 로그인 결과: {final.value}")
            return final
