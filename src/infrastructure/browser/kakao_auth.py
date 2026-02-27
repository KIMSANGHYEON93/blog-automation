"""KakaoAuth — Kakao account login for Tistory."""
import logging
import time

logger = logging.getLogger(__name__)

TISTORY_LOGIN_URL = "https://www.tistory.com/auth/kakao"


def kakao_login(sb, kakao_id: str, kakao_pw: str) -> bool:
    """카카오 계정으로 티스토리 로그인. 성공 시 True."""
    try:
        sb.open(TISTORY_LOGIN_URL)
        time.sleep(2)

        # 카카오 계정으로 로그인 버튼
        sb.click("a.btn_login.link_kakao_id")
        time.sleep(1)

        # ID/PW 입력
        sb.type("#loginId--1", kakao_id)
        sb.type("#password--2", kakao_pw)
        sb.click("button.btn_confirm")
        time.sleep(3)

        # 로그인 성공 확인 (티스토리 대시보드 URL 체크)
        current_url = sb.get_current_url()
        success = "tistory.com" in current_url and "auth" not in current_url
        logger.info(f"카카오 로그인 {'성공' if success else '실패'}: {current_url}")
        return success

    except Exception as e:
        logger.error(f"카카오 로그인 예외: {e}")
        return False
