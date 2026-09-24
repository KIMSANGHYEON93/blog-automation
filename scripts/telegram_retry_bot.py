"""텔레그램 재실행 봇 — 실패 알림의 /retry_publish, /retry_revise 를 받아 파이프라인을 다시 돌린다.

카카오 2FA를 제때 승인하지 못해 09:00 발행·10:00 수정이 실패했을 때, 폰에서 명령을 누르면
run_pipeline_b.sh 를 다시 실행한다(그러면 새 2FA 요청이 온다). launchd 가 상시 실행한다.

보안: TELEGRAM_CHAT_ID 에서 온 메시지만, 정해진 명령만 받는다. 받은 글자를 셸에 넘기지 않는다.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
RUN_SCRIPT = PROJECT_DIR / "run_pipeline_b.sh"
LOCK_DIR = PROJECT_DIR / ".pipeline_b.lock"
MAX_AGE_SECONDS = 600  # 봇이 꺼져 있던 동안 쌓인 오래된 명령은 실행하지 않는다
POLL_TIMEOUT = 50

COMMANDS: dict[str, list[str]] = {
    "/retry_publish": [],
    "/retry_revise": ["--revise"],
}

logger = logging.getLogger("telegram_retry_bot")


def command_args(update: dict, chat_id: str, now: float) -> list[str] | None:
    """허용된 채팅의 최근 재실행 명령이면 run_pipeline_b.sh 인자를, 아니면 None."""
    message = update.get("message") or {}
    if str(message.get("chat", {}).get("id")) != chat_id:
        return None
    if now - message.get("date", 0) > MAX_AGE_SECONDS:
        return None
    command = (message.get("text") or "").strip().split("@", 1)[0]
    return COMMANDS.get(command)


def _api(token: str, method: str, payload: dict, timeout: float = 10) -> dict:
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _reply(token: str, chat_id: str, text: str) -> None:
    try:
        _api(token, "sendMessage", {"chat_id": chat_id, "text": text})
    except Exception as e:
        logger.warning(f"답장 실패: {e}")


def _run(token: str, chat_id: str, args: list[str]) -> None:
    name = " ".join(args) or "발행"
    if LOCK_DIR.exists():
        _reply(token, chat_id, f"다른 파이프라인이 실행 중이라 {name} 재실행을 건너뜁니다.")
        return
    subprocess.Popen(
        ["/bin/bash", str(RUN_SCRIPT), *args],
        cwd=PROJECT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    logger.info(f"재실행 시작: {name}")
    _reply(token, chat_id, f"{name} 재실행 시작 — 카카오톡에서 2단계 인증을 승인하세요.")


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_DIR / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    offset = 0
    logger.info("텔레그램 재실행 봇 시작")
    while True:
        try:
            result = _api(
                token, "getUpdates",
                {"offset": offset, "timeout": POLL_TIMEOUT, "allowed_updates": ["message"]},
                timeout=POLL_TIMEOUT + 10,
            )
        except Exception as e:
            logger.warning(f"getUpdates 실패, 30초 후 재시도: {e}")
            time.sleep(30)
            continue
        for update in result.get("result", []):
            offset = update["update_id"] + 1
            args = command_args(update, chat_id, time.time())
            if args is not None:
                _run(token, chat_id, args)


if __name__ == "__main__":
    main()
