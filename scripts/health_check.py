"""운영 헬스 체크 — 읽기 전용 점검 후 이상이 있으면 텔레그램으로 요약 1건을 보낸다.

점검 항목: launchd 마지막 종료 코드·상주 서비스 PID, 당일 발행 결과(발행 로그), 로그 신선도,
`.pipeline_b.lock` 정체, n8n 컨테이너 상태, 전날 01:00(KST) n8n Content Generation 실행 여부.

아무것도 고치지 않는다(자동 복구 없음). 정상이면 보내지 않는다(`--daily-summary`면 정상도 1건).
`--dry-run`은 메시지만 출력하고 보내지 않는다. 비밀값(토큰 등)은 출력하지 않는다.

종료 코드: 0 정상, 1 이상 발견, 2 알림 전송 실패.
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

# run_pipeline_b.sh 와 같은 규약: BLOG_PROJECT_DIR 로 운영 저장소를 가리킬 수 있다(worktree 점검용)
PROJECT_DIR = Path(os.getenv("BLOG_PROJECT_DIR") or Path(__file__).resolve().parents[1])
LOG_DIR = PROJECT_DIR / "logs"
LOCK_DIR = PROJECT_DIR / ".pipeline_b.lock"

KST = timezone(timedelta(hours=9))
LABEL_PREFIX = "com.blog-automation."
RESIDENT = ("telegram-bot", "dashboard-hub")  # KeepAlive 서비스: PID가 있어야 정상
N8N_CONTAINER = "blog-automation-n8n-1"
N8N_WORKFLOW_NAME = "Blog Automation Pipeline A — Content Generation"
N8N_CRON_HOUR_KST = 1
PUBLISH_CHECK_AFTER_HOUR = 9  # 09:00 발행 이후에만 당일 발행 로그를 요구한다
LOCK_STALE_MINUTES = 120  # 정상 실행은 15분 안팎 — 2시간이 넘으면 정체
LOG_STALE_HOURS = 36
SUBPROCESS_TIMEOUT = 30

logger = logging.getLogger("health_check")

OK, WARN, ERROR = "OK", "WARN", "ERROR"


@dataclass(frozen=True)
class Finding:
    level: str
    check: str
    detail: str


# --- 순수 판정 함수 (테스트 대상) -------------------------------------------------------------

def parse_launchctl_list(text: str) -> dict:
    """`launchctl list` 출력에서 {짧은 이름: (pid 또는 None, 마지막 종료 코드)}."""
    jobs = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or not parts[2].startswith(LABEL_PREFIX):
            continue
        pid = None if parts[0] == "-" else int(parts[0])
        try:
            status = int(parts[1])
        except ValueError:
            continue
        jobs[parts[2][len(LABEL_PREFIX):]] = (pid, status)
    return jobs


def check_launchd(jobs: dict) -> list:
    if not jobs:
        return [Finding(ERROR, "launchd", "com.blog-automation.* 작업이 하나도 로드되지 않음")]
    findings = []
    for name, (pid, status) in sorted(jobs.items()):
        if name in RESIDENT and pid is None:
            findings.append(Finding(ERROR, "launchd", f"{name}: 상주 서비스가 실행 중이 아님"))
        elif status != 0:
            findings.append(Finding(ERROR, "launchd", f"{name}: 마지막 종료 코드 {status}"))
    return findings


def check_publish_log(log_dir: Path, now: datetime) -> list:
    """당일 09:00 발행 로그: 없음·비정상 종료·발행 0건을 잡는다."""
    if now.hour < PUBLISH_CHECK_AFTER_HOUR:
        return []
    logs = sorted(log_dir.glob(f"publish_{now:%Y%m%d}_*.log"))
    if not logs:
        return [Finding(WARN, "발행", "오늘 발행 로그 없음 (스케줄 미실행 또는 맥 절전)")]
    text = logs[-1].read_text(encoding="utf-8", errors="replace")
    exit_match = re.search(r"종료: .*\(exit=(\d+)\)", text)
    if not exit_match:
        return [Finding(WARN, "발행", "오늘 발행이 아직 끝나지 않았거나 종료 기록이 없음")]
    if "[SKIP]" in text:
        return [Finding(WARN, "발행", "다른 파이프라인 실행 중이라 오늘 발행이 건너뛰어짐")]
    code = int(exit_match.group(1))
    if code != 0:
        reason = re.findall(r"(\w+Error): (.+)", text)
        suffix = f" — {reason[-1][0]}: {reason[-1][1][:80]}" if reason else ""
        return [Finding(ERROR, "발행", f"오늘 발행 실패 (exit={code}){suffix}")]
    published = len(re.findall(r"publish_posts — 발행 완료:", text))
    ready = re.search(r"발행대기 (\d+)건 중 발행 가능 (\d+)건", text)
    if published == 0 and ready and int(ready.group(2)) > 0:
        return [Finding(WARN, "발행", f"발행 가능 {ready.group(2)}건인데 오늘 발행 0건")]
    if published == 0 and not ready:
        return [Finding(WARN, "발행", "오늘 발행 0건 (대기 글 정보 없음)")]
    return [Finding(OK, "발행", f"오늘 {published}건 발행")]


def check_log_freshness(log_dir: Path, now: datetime) -> list:
    stamps = [p.stat().st_mtime for p in log_dir.glob("*.log")] if log_dir.is_dir() else []
    if not stamps:
        return [Finding(WARN, "로그", "logs/ 에 로그 파일이 없음")]
    age = now - datetime.fromtimestamp(max(stamps), tz=KST)
    if age > timedelta(hours=LOG_STALE_HOURS):
        hours = int(age.total_seconds() // 3600)
        return [Finding(ERROR, "로그", f"가장 최근 로그가 {hours}시간 전")]
    return []


def check_lock(lock_dir: Path, now: datetime, pid_alive: Callable[[int], bool]) -> list:
    if not lock_dir.exists():
        return []
    age = now - datetime.fromtimestamp(lock_dir.stat().st_mtime, tz=KST)
    owner = lock_dir / "owner"
    raw = owner.read_text().strip() if owner.exists() else ""
    pid = int(raw) if raw.isdigit() else None
    if pid is not None and not pid_alive(pid):
        return [Finding(ERROR, "락", f"락 소유 프로세스(PID {pid})가 죽었는데 락이 남아 있음")]
    if age > timedelta(minutes=LOCK_STALE_MINUTES):
        minutes = int(age.total_seconds() // 60)
        return [Finding(ERROR, "락", f".pipeline_b.lock 이 {minutes}분째 유지됨")]
    return []


def last_cron_slot(now: datetime) -> datetime:
    """now 이전에 가장 최근에 지나간 01:00 KST."""
    slot = now.replace(hour=N8N_CRON_HOUR_KST, minute=0, second=0, microsecond=0)
    return slot if slot <= now else slot - timedelta(days=1)


def check_n8n_cron(executions: list, now: datetime) -> list:
    """executions: [(startedAt UTC naive, status)]. 가장 최근 01:00 슬롯 실행을 요구한다."""
    slot = last_cron_slot(now)
    if now - slot < timedelta(minutes=30):
        return []  # 방금 지난 슬롯은 아직 실행 중일 수 있다
    lo, hi = slot - timedelta(minutes=5), slot + timedelta(minutes=60)
    hits = [
        (started, status) for started, status in executions
        if lo <= started.replace(tzinfo=timezone.utc).astimezone(KST) <= hi
    ]
    label = f"{slot:%m/%d} 01:00"
    if not hits:
        return [Finding(ERROR, "n8n", f"{label} Content Generation 실행 기록 없음")]
    if not any(status == "success" for _, status in hits):
        return [Finding(ERROR, "n8n", f"{label} Content Generation 상태 {hits[-1][1]}")]
    return []


def render_message(findings: list, now: datetime) -> str | None:
    """이상(ERROR·WARN)이 있으면 본문, 없으면 None."""
    problems = [f for f in findings if f.level in (ERROR, WARN)]
    if not problems:
        return None
    lines = [f"운영 헬스 체크 {now:%m/%d %H:%M} — 이상 {len(problems)}건"]
    for f in sorted(problems, key=lambda x: x.level != ERROR):
        mark = "❌" if f.level == ERROR else "⚠️"
        lines.append(f"{mark} {f.check}: {f.detail}")
    return "\n".join(lines)


def render_summary(findings: list, now: datetime) -> str:
    oks = [f for f in findings if f.level == OK]
    detail = ", ".join(f.detail for f in oks) or "특이사항 없음"
    return f"운영 헬스 체크 {now:%m/%d %H:%M} — 정상 ({detail})"


# --- 외부 조회 (읽기 전용) --------------------------------------------------------------------

def _run(cmd: list) -> str:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT, check=True
    ).stdout


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def collect_launchd() -> list:
    try:
        return check_launchd(parse_launchctl_list(_run(["launchctl", "list"])))
    except (OSError, subprocess.SubprocessError) as e:
        return [Finding(WARN, "launchd", f"launchctl 조회 실패: {type(e).__name__}")]


_N8N_QUERY = (
    "const s=require('sqlite3');"
    "const db=new s.Database('/home/node/.n8n/database.sqlite',s.OPEN_READONLY);"
    "db.all(\"select e.startedAt as t,e.status as s from execution_entity e "
    "join workflow_entity w on w.id=e.workflowId where w.name=? "
    "order by e.startedAt desc limit 5\",[process.argv[1]],"
    "(e,r)=>{if(e){console.error(e.message);process.exit(1)}console.log(JSON.stringify(r))});"
)


def collect_n8n(now: datetime) -> list:
    try:
        state = _run(["docker", "inspect", "-f", "{{.State.Status}}", N8N_CONTAINER]).strip()
    except (OSError, subprocess.SubprocessError):
        return [Finding(ERROR, "n8n", "Docker에 접근할 수 없거나 n8n 컨테이너가 없음")]
    if state != "running":
        return [Finding(ERROR, "n8n", f"컨테이너 상태 {state}")]
    try:
        out = _run([
            "docker", "exec", "-w", "/usr/local/lib/node_modules/n8n", N8N_CONTAINER,
            "node", "-e", _N8N_QUERY, N8N_WORKFLOW_NAME,
        ])
        rows = json.loads(out)
        executions = [(datetime.strptime(r["t"][:19], "%Y-%m-%d %H:%M:%S"), r["s"]) for r in rows]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return [Finding(WARN, "n8n", "실행 이력 조회 실패 (컨테이너는 실행 중)")]
    return check_n8n_cron(executions, now)


def run_checks(now: datetime) -> list:
    findings = []
    findings += collect_launchd()
    findings += check_publish_log(LOG_DIR, now)
    findings += check_log_freshness(LOG_DIR, now)
    findings += check_lock(LOCK_DIR, now, _pid_alive)
    findings += collect_n8n(now)
    return findings


# --- 전송 -------------------------------------------------------------------------------------

def send_telegram(text: str, level: str) -> bool:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_DIR / ".env")
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not (token and chat_id):
        logger.error("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 가 설정돼 있지 않아 보내지 못함")
        return False
    sys.path.insert(0, str(PROJECT_DIR))
    from src.infrastructure.notification.telegram_adapter import TelegramNotificationAdapter

    # 어댑터가 parse_mode=HTML 로 보내므로 본문의 <, & 는 이스케이프한다
    return TelegramNotificationAdapter(bot_token=token, chat_id=chat_id).send(
        html.escape(text), level=level
    )


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="메시지만 출력하고 보내지 않는다")
    parser.add_argument(
        "--daily-summary", action="store_true", help="정상일 때도 요약 1건을 보낸다"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    now = datetime.now(KST)
    findings = run_checks(now)
    problem = render_message(findings, now)
    healthy = problem is None
    message = problem or (render_summary(findings, now) if args.daily_summary else None)
    has_error = any(f.level == ERROR for f in findings)

    if message is None:
        logger.info("정상 — 보낼 알림 없음")
        return 0
    if args.dry_run:
        print(message)
        return 0 if healthy else 1
    sent = send_telegram(message, "INFO" if healthy else ("ERROR" if has_error else "WARNING"))
    if not sent:
        return 2
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
