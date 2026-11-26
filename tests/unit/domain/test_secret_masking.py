"""mask_secrets — 로그·오류 문자열에서 API 키·토큰 값을 가린다 (가짜 값만 사용)."""
from __future__ import annotations

import pytest

from src.domain.services.secret_masking import MASK, mask_secrets

FAKE_GOOGLE_KEY = "AIzaSyFAKE_key-0123456789abcdefghijklmn"
FAKE_BOT_TOKEN = "123456789:AAFakeBotToken_abc-DEF0123456789xyz"


def test_구글_API_키_패턴을_가린다():
    text = f"키 {FAKE_GOOGLE_KEY} 로 호출"
    assert mask_secrets(text) == f"키 {MASK} 로 호출"


def test_PageSpeed_예외_문자열의_key_쿼리를_가린다():
    text = (
        "429 Client Error: Too Many Requests for url: "
        "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        f"?url=https%3A%2F%2Fx.tistory.com%2F1&strategy=mobile&key={FAKE_GOOGLE_KEY}"
    )
    masked = mask_secrets(text)
    assert FAKE_GOOGLE_KEY not in masked
    assert "AIza" not in masked
    assert "429" in masked  # cli의 한도 초과 감지가 깨지면 안 된다
    assert "strategy=mobile" in masked
    assert masked.endswith(f"key={MASK}")


@pytest.mark.parametrize("name", ["key", "api_key", "token", "access_token", "API_KEY"])
def test_비밀_쿼리_파라미터_값을_가린다(name):
    text = f"https://example.com/search.json?q=k8s&{name}=s3cr3t-Value_1&hl=ko"
    masked = mask_secrets(text)
    assert "s3cr3t-Value_1" not in masked
    assert f"{name}={MASK}&hl=ko" in masked
    assert "q=k8s" in masked


def test_비밀이_아닌_파라미터는_그대로_둔다():
    text = "https://example.com/?monkey=1&keyword=docker&tokens=3"
    assert mask_secrets(text) == text


def test_텔레그램_봇_토큰을_가린다():
    text = f"<urlopen error> https://api.telegram.org/bot{FAKE_BOT_TOKEN}/sendMessage"
    masked = mask_secrets(text)
    assert FAKE_BOT_TOKEN not in masked
    assert "AAFakeBotToken" not in masked
    assert f"api.telegram.org/bot{MASK}/sendMessage" in masked


def test_비밀이_없으면_그대로():
    assert mask_secrets("HTTP Error 401: Unauthorized") == "HTTP Error 401: Unauthorized"
    assert mask_secrets("") == ""


def test_문자열이_아닌_값도_받는다():
    assert FAKE_GOOGLE_KEY not in mask_secrets(ValueError(f"bad key {FAKE_GOOGLE_KEY}"))


def test_슬랙_웹훅_경로를_가린다():
    text = "fail https://hooks.slack.com/services/T0FAKE/B0FAKE/fakeSecretPart123 down"
    masked = mask_secrets(text)
    assert "fakeSecretPart123" not in masked
    assert f"hooks.slack.com/services/{MASK} down" in masked
