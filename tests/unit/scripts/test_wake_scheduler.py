"""wake-scheduler.sh — 가짜 pmset 으로 예약 규칙을 확인한다(실제 pmset·root 불필요)."""
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_WAKE_DIR = Path(__file__).resolve().parents[3] / "scripts" / "wake"
_SCRIPT = _WAKE_DIR / "wake-scheduler.sh"
_FMT = "%m/%d/%Y %H:%M:%S"
_TIMES = {"00:55:00", "08:55:00"}


@pytest.fixture
def run(tmp_path):
    """가짜 pmset 으로 스크립트를 돌려 예약된 시각 목록을 돌려준다."""

    def _run(sched_text=""):
        sched = tmp_path / "sched.txt"
        calls = tmp_path / "calls.txt"
        sched.write_text(sched_text)
        calls.write_text("")
        fake = tmp_path / "pmset"
        fake.write_text(
            "#!/bin/bash\n"
            f'if [ "$1" = "-g" ]; then cat "{sched}"; exit 0; fi\n'
            f'echo "$*" >> "{calls}"\n'
        )
        fake.chmod(0o755)
        script = tmp_path / "wake-scheduler.sh"
        text = _SCRIPT.read_text(encoding="utf-8")
        assert "PMSET=/usr/bin/pmset" in text
        script.write_text(text.replace("PMSET=/usr/bin/pmset", f"PMSET={fake}"))
        subprocess.run(["/bin/bash", str(script)], check=True, capture_output=True)
        return [line.split(" ", 2)[2] for line in calls.read_text().splitlines()]

    return _run


def test_bash_문법이_맞다():
    for name in ("wake-scheduler.sh", "install.sh", "uninstall.sh"):
        subprocess.run(["/bin/bash", "-n", str(_WAKE_DIR / name)], check=True)


def test_앞으로_며칠의_정해진_시각만_예약한다(run):
    stamps = run()
    assert stamps, "예약이 하나도 없음"
    now = datetime.now()
    for stamp in stamps:
        when = datetime.strptime(stamp, _FMT)
        assert when > now
        assert when.strftime("%H:%M:%S") in _TIMES
        assert when.date() <= (now + timedelta(days=3)).date()
    assert len(stamps) == len(set(stamps))


def test_내일_두_시각은_반드시_예약된다(run):
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%m/%d/%Y")
    stamps = run()
    assert f"{tomorrow} 00:55:00" in stamps
    assert f"{tomorrow} 08:55:00" in stamps


def test_이미_예약된_시각은_다시_예약하지_않는다(run):
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%m/%d/%Y")
    existing = (
        "Scheduled power events:\n"
        f" [0]  wake at {tomorrow} 00:55:00 by 'pmset'\n"
        f" [1]  wake at {tomorrow} 08:55:00 by 'pmset'\n"
    )
    stamps = run(existing)
    assert f"{tomorrow} 00:55:00" not in stamps
    assert f"{tomorrow} 08:55:00" not in stamps
    assert stamps, "나머지 날짜는 예약돼야 함"


def test_pmset_schedule_wake_외의_명령은_쓰지_않는다():
    text = _SCRIPT.read_text(encoding="utf-8")
    pmset_uses = re.findall(r'"\$PMSET" (-g sched|schedule wake|\S+)', text)
    assert sorted(set(pmset_uses)) == ["-g sched", "schedule wake"]
    assert "sudo" not in text and "eval" not in text
