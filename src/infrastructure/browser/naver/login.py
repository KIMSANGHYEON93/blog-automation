"""네이버 자동 로그인 — 폰에서 세션을 되살리기 위한 대시보드 '네이버 다시 로그인' 전용.

버튼 1회에 제출 1회만 한다. 실패가 반복되면 네이버가 보호조치를 걸기 때문이다.
아이디·비밀번호는 입력란에 값으로만 넣고 로그·메시지·예외에 남기지 않는다.
"""
from __future__ import annotations

from enum import Enum

from src.infrastructure.browser.naver import selectors as sel

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
