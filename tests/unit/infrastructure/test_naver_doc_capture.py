"""공식 문서 캡처 — 열리지 않거나 다른 사이트로 넘어가는 주소는 캡처하지 않는다."""
from src.infrastructure.browser.naver.doc_capture import is_same_site


def test_같은_사이트로의_이동은_허용():
    assert is_same_site("https://www.canva.com/help", "https://canva.com/ko_kr/help/")
    assert is_same_site("https://support.google.com/gemini", "https://support.google.com/gemini/?hl=ko")


def test_다른_사이트로_넘어가면_거부():
    # 존재하지 않는 페이지가 로그인·홈·다른 도메인으로 튕기는 경우
    assert not is_same_site("https://learn.chatgpt.com/docs/prompting", "https://openai.com/")
