"""KakaoAuth — Kakao account login for Tistory (2026-02 updated).

Flow: 티스토리 로그인 → '카카오계정으로 로그인' 클릭 → 카카오 OAuth → 티스토리 세션 생성
"""
import logging
import time
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

TISTORY_LOGIN_URL = "https://www.tistory.com/auth/login"
TWO_FA_WAIT_SEC = 120


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


def _enter_credentials_and_wait(sb, kakao_id: str, kakao_pw: str) -> bool:
    """카카오 로그인 폼에 ID/PW 입력 후 2FA 처리."""
    try:
        sb.wait_for_element_present("#loginId--1", timeout=10)
        sb.type("#loginId--1", kakao_id)
        time.sleep(0.5)

        sb.type("#password--2", kakao_pw)
        time.sleep(0.5)

        sb.click("button.submit")
        time.sleep(5)

        current_url = sb.get_current_url()

        # 2FA 감지
        if "twoStepVerification" in current_url or "twostep" in current_url.lower():
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
        if "accounts.kakao" not in current_url:
            logger.info(f"리다이렉트 감지 ({elapsed}초): {current_url}")
            return _is_tistory_logged_in(current_url)

        if elapsed % 15 == 0:
            logger.info(f"  대기 중... {elapsed}초")

    logger.error(f"2FA 타임아웃 ({TWO_FA_WAIT_SEC}초)")
    return False


def _is_tistory_logged_in(url: str) -> bool:
    """URL hostname 기반으로 티스토리 로그인 성공 여부 판별."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return host.endswith("tistory.com") and "/auth/login" not in parsed.path
