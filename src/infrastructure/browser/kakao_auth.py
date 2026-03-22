"""KakaoAuth — Kakao account login for Tistory (2026-02 updated).

Flow: 티스토리 로그인 → '카카오계정으로 로그인' 클릭 → 카카오 OAuth → 티스토리 세션 생성
"""
from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

TISTORY_LOGIN_URL = "https://www.tistory.com/auth/login"
TWO_FA_WAIT_SEC = 120

# --- 카카오 로그인 폼 셀렉터 Fallback Chain ---
# React가 생성하는 불안정 ID(#loginId--1 등)를 최상위에 유지하되,
# 안정적인 name/type/id-prefix 셀렉터를 fallback으로 추가
KAKAO_LOGIN_ID_SELECTORS = [
    "#loginId--1",              # React 생성 ID (기존 — 작동 시 최우선)
    "input[name='loginId']",    # name 속성 기반 (안정)
    "input[type='email']",      # type 기반 (범용)
    "input[id^='loginId']",     # id prefix 매칭 (--2, --3 등 대응)
]

KAKAO_PASSWORD_SELECTORS = [
    "#password--2",             # React 생성 ID (기존)
    "input[name='password']",   # name 속성 기반 (안정)
    "input[type='password']",   # type 기반 (범용)
    "input[id^='password']",    # id prefix 매칭
]

KAKAO_SUBMIT_SELECTORS = [
    "button.submit",            # class 기반 (기존)
    "button[type='submit']",    # type 기반 (범용)
]


def kakao_login(sb, kakao_id: str, kakao_pw: str) -> bool:
    """티스토리 로그인 (카카오 OAuth 경유). 성공 시 True."""
    try:
        # 1) 티스토리 로그인 페이지 진입
        sb.open(TISTORY_LOGIN_URL)
        time.sleep(2)

        # 2) "카카오계정으로 로그인" 버튼 클릭
        kakao_btn_selectors = [
            "a.btn_login.link_kakao_id",
            "a[class*='kakao']",
            "//a[contains(text(), '카카오')]",
            "//button[contains(text(), '카카오')]",
        ]
        clicked = False
        for sel in kakao_btn_selectors:
            try:
                if sel.startswith("//"):
                    sb.click(sel)
                else:
                    if sb.is_element_visible(sel):
                        sb.click(sel)
                clicked = True
                logger.info(f"카카오 로그인 버튼 클릭: {sel}")
                break
            except Exception:
                continue

        if not clicked:
            # JS로 카카오 로그인 링크 찾기 (fallback)
            kakao_href = sb.execute_script("""
                var links = document.querySelectorAll('a');
                for (var i = 0; i < links.length; i++) {
                    var text = links[i].textContent || '';
                    var href = links[i].href || '';
                    if (text.indexOf('카카오') !== -1 || href.indexOf('kakao') !== -1) {
                        return links[i].href;
                    }
                }
                return null;
            """)
            if kakao_href:
                sb.open(kakao_href)
                clicked = True
                logger.info(f"카카오 로그인 링크 JS fallback: {kakao_href}")
            else:
                logger.error("카카오 로그인 버튼을 찾을 수 없음")
                return False

        # 3) 리다이렉트 안정화 대기 (최대 15초 폴링)
        stable_url = None
        for _ in range(15):
            time.sleep(1)
            current_url = sb.get_current_url()
            if current_url == stable_url:
                break
            stable_url = current_url

        current_url = sb.get_current_url()
        logger.info(f"카카오 버튼 클릭 후 URL: {current_url}")

        # 카카오 로그인 페이지인 경우 → ID/PW 입력
        if "accounts.kakao" in current_url:
            return _enter_credentials_and_wait(sb, kakao_id, kakao_pw)

        # 이미 카카오 로그인 된 경우 (쿠키 유지) → 바로 티스토리로 리다이렉트
        if _is_tistory_logged_in(current_url):
            logger.info("쿠키로 자동 로그인 성공")
            return True

        # 예상 외 URL
        logger.warning(f"예상 외 URL: {current_url}")
        return _is_tistory_logged_in(current_url)

    except Exception as e:
        logger.error(f"카카오 로그인 예외: {e}")
        return False


def _find_kakao_element(sb, selectors: list[str], timeout: int = 10) -> str | None:
    """Fallback Chain으로 첫 번째 존재하는 카카오 로그인 셀렉터 반환.

    dom_selectors.find_element()와 동일 패턴.
    """
    per_timeout = max(1, timeout // len(selectors))
    for selector in selectors:
        try:
            sb.wait_for_element_present(selector, timeout=per_timeout)
            logger.debug(f"카카오 셀렉터 발견: {selector}")
            return selector
        except Exception:
            continue
    return None


def _find_kakao_elements_by_js(sb) -> dict[str, str] | None:
    """최종 fallback: JS로 페이지의 모든 input을 순회하여 구조 기반 탐색.

    email→password→submit 순서로 폼 요소를 찾아 임시 ID를 부여한 뒤 반환.
    """
    result = sb.execute_script("""
        var inputs = document.querySelectorAll('input');
        var emailEl = null, pwEl = null;
        for (var i = 0; i < inputs.length; i++) {
            var inp = inputs[i];
            var t = (inp.type || '').toLowerCase();
            var n = (inp.name || '').toLowerCase();
            if (!emailEl && (t === 'email' || t === 'text' || n === 'loginid'
                || n === 'email' || n === 'username' || n === 'login_id')) {
                emailEl = inp;
            } else if (!pwEl && (t === 'password' || n === 'password')) {
                pwEl = inp;
            }
        }
        var submitEl = document.querySelector(
            'button[type="submit"], button.submit, input[type="submit"]'
        );
        if (!emailEl || !pwEl) return null;

        // 임시 data 속성 부여
        emailEl.setAttribute('data-kakao-auto', 'loginId');
        pwEl.setAttribute('data-kakao-auto', 'password');
        if (submitEl) submitEl.setAttribute('data-kakao-auto', 'submit');

        return {
            loginId: '[data-kakao-auto="loginId"]',
            password: '[data-kakao-auto="password"]',
            submit: submitEl ? '[data-kakao-auto="submit"]' : null
        };
    """)
    if result:
        logger.info(f"JS fallback으로 카카오 로그인 폼 발견: {result}")
        return dict(result)  # type: ignore[arg-type]
    return None


def _enter_credentials_and_wait(sb, kakao_id: str, kakao_pw: str) -> bool:
    """카카오 로그인 폼에 ID/PW 입력 후 2FA 처리."""
    try:
        # 셀렉터 탐색: Fallback Chain → JS 구조 탐색
        id_sel = _find_kakao_element(sb, KAKAO_LOGIN_ID_SELECTORS, timeout=10)
        pw_sel = _find_kakao_element(sb, KAKAO_PASSWORD_SELECTORS, timeout=5)
        submit_sel = _find_kakao_element(sb, KAKAO_SUBMIT_SELECTORS, timeout=3)

        # Chain 실패 시 JS 구조 기반 최종 fallback
        if not id_sel or not pw_sel:
            logger.warning("셀렉터 chain 실패 — JS 구조 탐색 시도")
            js_result = _find_kakao_elements_by_js(sb)
            if not js_result:
                logger.error("카카오 로그인 폼을 찾을 수 없음 (셀렉터 + JS 모두 실패)")
                return False
            id_sel = js_result["loginId"]
            pw_sel = js_result["password"]
            submit_sel = js_result.get("submit") or submit_sel

        logger.info(f"카카오 로그인 셀렉터: id={id_sel}, pw={pw_sel}, submit={submit_sel}")

        time.sleep(1)

        # 방법 1: SeleniumBase 네이티브 타이핑
        try:
            sb.click(id_sel)
            sb.type(id_sel, kakao_id)
            time.sleep(0.5)
            sb.click(pw_sel)
            sb.type(pw_sel, kakao_pw)
            time.sleep(0.5)
            if submit_sel:
                sb.click(submit_sel)
        except Exception as type_err:
            logger.warning(f"네이티브 타이핑 실패, JS fallback: {type_err}")
            # JS로 직접 입력 — arguments[]로 안전하게 인자 전달 (문자열 보간 없음)
            sb.execute_script("""
                var idSel = arguments[0];
                var pwSel = arguments[1];
                var submitSel = arguments[2];
                var idVal = arguments[3];
                var pwVal = arguments[4];
                function setNativeValue(el, value) {
                    var setter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    setter.call(el, value);
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }
                var loginId = document.querySelector(idSel);
                var pw = document.querySelector(pwSel);
                if (loginId) setNativeValue(loginId, idVal);
                if (pw) setNativeValue(pw, pwVal);
                var btn = document.querySelector(submitSel);
                if (btn) btn.click();
            """, id_sel, pw_sel, submit_sel or "button.submit",
                kakao_id, kakao_pw)

        time.sleep(5)

        current_url = sb.get_current_url()

        # 2FA 감지 (URL 또는 페이지 제목/본문 기반)
        is_2fa = (
            "twoStepVerification" in current_url
            or "twostep" in current_url.lower()
        )
        if not is_2fa and "accounts.kakao" in current_url:
            page_title = sb.get_title() or ""
            if "2단계 인증" in page_title or "보안" in page_title:
                is_2fa = True

        if is_2fa:
            logger.info("2단계 인증 감지 — 카카오톡에서 승인 대기...")
            return _handle_two_fa(sb)

        return _is_tistory_logged_in(current_url)

    except Exception as e:
        logger.error(f"카카오 자격증명 입력 예외: {e}")
        return False


def _handle_two_fa(sb) -> bool:
    """2FA: '이 브라우저에서 2단계 인증 사용 안 함' 체크 + 승인 대기."""
    # 스킵 체크박스 클릭 시도
    try:
        skip_selectors = [
            "label[for='skipTwoStepVerification']",
            "input#skipTwoStepVerification",
            "span.label_check",
        ]
        for sel in skip_selectors:
            try:
                if sb.is_element_visible(sel):
                    sb.click(sel)
                    logger.info(f"2FA 스킵 체크박스 클릭: {sel}")
                    break
            except Exception:
                continue
    except Exception:
        pass

    # 카카오톡 승인 대기 (폴링)
    logger.info(f"카카오톡 승인 대기 (최대 {TWO_FA_WAIT_SEC}초)...")
    elapsed = 0
    poll_interval = 3
    while elapsed < TWO_FA_WAIT_SEC:
        time.sleep(poll_interval)
        elapsed += poll_interval
        current_url = sb.get_current_url()

        if _is_tistory_logged_in(current_url):
            logger.info(f"2FA 승인 완료 → 티스토리 로그인 성공 ({elapsed}초)")
            return True

        # 카카오 인증 완료 → 다른 URL로 이동한 경우
        # kauth.kakao.com → tistory.com 리다이렉트 체인 완료 대기
        if "accounts.kakao" not in current_url:
            logger.info(f"리다이렉트 감지 ({elapsed}초): {current_url[:80]}")
            time.sleep(2)
            # kauth 계정 확인 페이지: "계속하기" 버튼 자동 클릭
            if "kauth.kakao.com" in sb.get_current_url():
                _click_kauth_continue(sb)
                time.sleep(3)
            # 최종 tistory.com 도달까지 추가 대기 (최대 15초)
            for _ in range(15):
                time.sleep(1)
                final_url = sb.get_current_url()
                if _is_tistory_logged_in(final_url):
                    logger.info(f"2FA 승인 → 티스토리 로그인 완료: {final_url}")
                    return True
            logger.warning(f"리다이렉트 후 티스토리 미도달: {sb.get_current_url()}")
            return _is_tistory_logged_in(sb.get_current_url())

        if elapsed % 15 == 0:
            logger.info(f"  대기 중... {elapsed}초")

    logger.error(f"2FA 타임아웃 ({TWO_FA_WAIT_SEC}초)")
    return False


def _click_kauth_continue(sb) -> None:
    """kauth.kakao.com 계정 확인 페이지에서 '계속하기' 버튼 클릭."""
    try:
        sb.execute_script("""
            var btn = document.querySelector('button.btn_agree');
            if (btn) { btn.click(); return; }
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                if (buttons[i].textContent.trim() === '계속하기') {
                    buttons[i].click(); return;
                }
            }
        """)
        logger.info("kauth '계속하기' 버튼 클릭")
    except Exception as e:
        logger.warning(f"kauth 계속하기 클릭 실패: {e}")


def _is_tistory_logged_in(url: str) -> bool:
    """URL hostname 기반으로 티스토리 로그인 성공 여부 판별."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return host.endswith("tistory.com") and "/auth/login" not in parsed.path
