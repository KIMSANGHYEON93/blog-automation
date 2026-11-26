"""로그·오류 문자열에서 API 키·토큰 값을 가린다 (stdlib만 사용).

requests 예외는 `... for url: https://...?key=AIza...`처럼 요청 URL 전체를 담는다.
이 문자열을 로그·시트·알림에 넘기기 전에 `mask_secrets`를 거친다.
"""
from __future__ import annotations

import re

MASK = "***"

# Google API 키 (PageSpeed·GSC 등) — 쿼리 이름과 상관없이 값 자체를 찾는다
_GOOGLE_KEY = re.compile(r"AIza[0-9A-Za-z_-]+")
# 쿼리·폼 파라미터: key, api_key, token, access_token (대소문자 무시, 이름 경계 확인)
_SECRET_PARAM = re.compile(
    r"(?i)(?<![0-9A-Za-z_])((?:api_|access_)?(?:key|token))=([^&\s#'\"<>]+)"
)
# Telegram Bot API 경로: /bot<id>:<token>/
_TELEGRAM_BOT = re.compile(r"(/bot)\d+:[0-9A-Za-z_-]+")
# Slack Incoming Webhook: 경로 전체가 비밀이다
_SLACK_WEBHOOK = re.compile(r"(hooks\.slack\.com/services/)[0-9A-Za-z_/-]+")


def mask_secrets(value: object) -> str:
    """키·토큰 값을 MASK로 바꾼 문자열을 돌려준다. 원본은 바꾸지 않는다."""
    text = str(value)
    text = _TELEGRAM_BOT.sub(rf"\1{MASK}", text)
    text = _SLACK_WEBHOOK.sub(rf"\1{MASK}", text)
    text = _SECRET_PARAM.sub(rf"\1={MASK}", text)
    return _GOOGLE_KEY.sub(MASK, text)
