"""운영 헬스 체크 — 이상 판정 규칙(외부 호출 없는 순수 함수)."""
import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "health_check.py"
_spec = importlib.util.spec_from_file_location("health_check", _SCRIPT)
hc = importlib.util.module_from_spec(_spec)
sys.modules["health_check"] = hc  # dataclass 가 모듈을 찾는다
_spec.loader.exec_module(hc)

NOW = datetime(2026, 11, 25, 9, 30, tzinfo=hc.KST)


def _levels(findings):
    return [f.level for f in findings]


def test_launchctl_출력을_이름_pid_종료코드로_해석한다():
    text = (
        "PID\tStatus\tLabel\n"
        "-\t0\tcom.blog-automation.revise\n"
        "1292\t0\tcom.blog-automation.telegram-bot\n"
        "-\t1\tcom.blog-automation.publish\n"
        "-\t0\tcom.apple.other\n"
    )
    assert hc.parse_launchctl_list(text) == {
        "revise": (None, 0), "telegram-bot": (1292, 0), "publish": (None, 1),
    }


def test_launchd_종료코드가_0이_아니면_오류():
    findings = hc.check_launchd({"publish": (None, 1), "revise": (None, 0)})
    assert len(findings) == 1 and "publish" in findings[0].detail


def test_launchd_상주_서비스는_pid가_없으면_오류():
    assert _levels(hc.check_launchd({"telegram-bot": (None, 0)})) == [hc.ERROR]
    assert hc.check_launchd({"telegram-bot": (1292, 0)}) == []


def test_launchd_작업이_하나도_없으면_오류():
    assert _levels(hc.check_launchd({})) == [hc.ERROR]


def _write_publish_log(tmp_path, body):
    path = tmp_path / "publish_20261125_090002.log"
    path.write_text(body, encoding="utf-8")


def test_발행_로그가_없으면_경고(tmp_path):
    assert _levels(hc.check_publish_log(tmp_path, NOW)) == [hc.WARN]


def test_발행_시각_전에는_점검하지_않는다(tmp_path):
    assert hc.check_publish_log(tmp_path, NOW.replace(hour=8)) == []


def test_발행_실패는_원인과_함께_오류(tmp_path):
    _write_publish_log(
        tmp_path,
        "src.domain.exceptions.LoginFailedError: Tistory 로그인 실패 — 발행 중단\n"
        "=== Pipeline B [publish] 종료: 2026-11-25 09:00:31 (exit=1) ===\n",
    )
    [finding] = hc.check_publish_log(tmp_path, NOW)
    assert finding.level == hc.ERROR and "LoginFailedError" in finding.detail


def test_발행_성공은_건수를_센다(tmp_path):
    _write_publish_log(
        tmp_path,
        "x publish_posts — 발행대기 3건 중 발행 가능 2건\n"
        "x publish_posts — 발행 완료: A → u\nx publish_posts — 발행 완료: B → u\n"
        "=== Pipeline B [publish] 종료: 2026-11-25 09:13:35 (exit=0) ===\n",
    )
    [finding] = hc.check_publish_log(tmp_path, NOW)
    assert finding.level == hc.OK and "2건" in finding.detail


def test_발행_가능한데_0건이면_경고(tmp_path):
    _write_publish_log(
        tmp_path,
        "x publish_posts — 발행대기 3건 중 발행 가능 2건\n"
        "=== Pipeline B [publish] 종료: 2026-11-25 09:13:35 (exit=0) ===\n",
    )
    assert _levels(hc.check_publish_log(tmp_path, NOW)) == [hc.WARN]


def test_다른_파이프라인_때문에_건너뛴_발행은_경고(tmp_path):
    _write_publish_log(
        tmp_path,
        "[SKIP] 다른 파이프라인 실행 중 — publish 스킵\n"
        "=== Pipeline B [publish] 종료: 2026-11-25 09:00:02 (exit=0) ===\n",
    )
    assert _levels(hc.check_publish_log(tmp_path, NOW)) == [hc.WARN]


def test_로그가_36시간_넘게_없으면_오류(tmp_path):
    log = tmp_path / "a.log"
    log.write_text("x")
    old = (NOW - timedelta(hours=40)).timestamp()
    os.utime(log, (old, old))
    assert _levels(hc.check_log_freshness(tmp_path, NOW)) == [hc.ERROR]


def test_최근_로그는_정상(tmp_path):
    log = tmp_path / "a.log"
    log.write_text("x")
    assert hc.check_log_freshness(tmp_path, datetime.now(hc.KST)) == []


def test_락이_없으면_정상(tmp_path):
    assert hc.check_lock(tmp_path / "none", NOW, lambda pid: True) == []


def test_락_소유_프로세스가_죽었으면_오류(tmp_path):
    lock = tmp_path / ".pipeline_b.lock"
    lock.mkdir()
    (lock / "owner").write_text("4242")
    assert _levels(hc.check_lock(lock, datetime.now(hc.KST), lambda pid: False)) == [hc.ERROR]


def test_락이_오래_유지되면_오류(tmp_path):
    lock = tmp_path / ".pipeline_b.lock"
    lock.mkdir()
    (lock / "owner").write_text("4242")
    old = (NOW - timedelta(hours=3)).timestamp()
    os.utime(lock, (old, old))
    assert _levels(hc.check_lock(lock, NOW, lambda pid: True)) == [hc.ERROR]


def test_살아있는_짧은_락은_정상(tmp_path):
    lock = tmp_path / ".pipeline_b.lock"
    lock.mkdir()
    (lock / "owner").write_text("4242")
    assert hc.check_lock(lock, datetime.now(hc.KST), lambda pid: True) == []


def _utc(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def test_n8n_전날_0100_실행이_있으면_정상():
    # 11/24 16:00 UTC = 11/25 01:00 KST
    assert hc.check_n8n_cron([(_utc("2026-11-24 16:00:00"), "success")], NOW) == []


def test_n8n_0100_실행_기록이_없으면_오류():
    findings = hc.check_n8n_cron([(_utc("2026-11-20 16:00:00"), "success")], NOW)
    assert _levels(findings) == [hc.ERROR] and "11/25 01:00" in findings[0].detail


def test_n8n_실행이_실패_상태면_오류():
    findings = hc.check_n8n_cron([(_utc("2026-11-24 16:00:00"), "error")], NOW)
    assert _levels(findings) == [hc.ERROR]


def test_n8n_0100_직후에는_판정을_미룬다():
    early = NOW.replace(hour=1, minute=10)
    assert hc.check_n8n_cron([], early) == []


def test_n8n_새벽_0030에는_전날_슬롯을_본다():
    assert hc.last_cron_slot(NOW.replace(hour=0, minute=30)).day == 24


def test_이상이_없으면_메시지가_없다():
    assert hc.render_message([hc.Finding(hc.OK, "발행", "오늘 1건 발행")], NOW) is None


def test_이상은_오류를_앞에_두고_한_건으로_묶는다():
    findings = [
        hc.Finding(hc.WARN, "로그", "w"),
        hc.Finding(hc.ERROR, "발행", "e"),
        hc.Finding(hc.OK, "발행", "ok"),
    ]
    lines = hc.render_message(findings, NOW).splitlines()
    assert "이상 2건" in lines[0]
    assert lines[1].startswith("❌") and lines[2].startswith("⚠️")


def test_일일_요약은_정상_내용을_담는다():
    text = hc.render_summary([hc.Finding(hc.OK, "발행", "오늘 1건 발행")], NOW)
    assert "정상" in text and "오늘 1건 발행" in text


def test_캡차_차단_표시가_오늘이면_차단_중으로_본다(tmp_path):
    block = tmp_path / "kakao_challenge_block.json"
    block.write_text(json.dumps({"blocked_on": "2026-11-25", "reason": "보안문제"}))
    assert hc.kakao_blocked_today(block, NOW) is True


def test_캡차_차단_표시가_어제거나_없거나_깨졌으면_차단_아님(tmp_path):
    block = tmp_path / "kakao_challenge_block.json"
    assert hc.kakao_blocked_today(block, NOW) is False
    block.write_text(json.dumps({"blocked_on": "2026-11-24"}))
    assert hc.kakao_blocked_today(block, NOW) is False
    block.write_text("not json")
    assert hc.kakao_blocked_today(block, NOW) is False
    block.write_text("[]")
    assert hc.kakao_blocked_today(block, NOW) is False


def test_차단_중이면_로그인_실패성_이상을_한_줄로_묶는다():
    findings = [
        hc.Finding(hc.ERROR, "launchd", "publish: 마지막 종료 코드 1"),
        hc.Finding(hc.ERROR, "launchd", "revise: 마지막 종료 코드 1"),
        hc.Finding(hc.ERROR, "발행", "오늘 발행 실패 (exit=1)"),
        hc.Finding(hc.ERROR, "launchd", "check-index: 마지막 종료 코드 1"),
        hc.Finding(hc.ERROR, "n8n", "컨테이너 상태 exited"),
    ]
    folded = hc.fold_kakao_block(findings, True)
    assert folded[0].check == "카카오" and "tistory_login.py" in folded[0].detail
    rest = [f.detail for f in folded[1:]]
    assert rest == ["check-index: 마지막 종료 코드 1", "컨테이너 상태 exited"]


def test_차단이_아니면_이상을_그대로_둔다():
    findings = [hc.Finding(hc.ERROR, "발행", "오늘 발행 실패 (exit=1)")]
    assert hc.fold_kakao_block(findings, False) == findings


def test_실행_중인_작업은_이전_종료_코드를_무시한다():
    # 재시작된 상주 서비스는 PID가 있고 마지막 종료 코드(-15 등)는 이전 인스턴스의 것이다
    assert hc.check_launchd({"dashboard-hub": (94815, -15), "telegram-bot": (1292, 0)}) == []


def test_조회는_일시_실패하면_한_번_더_시도한다(monkeypatch):
    import subprocess
    from types import SimpleNamespace

    outcomes = [subprocess.TimeoutExpired("docker", 1), SimpleNamespace(stdout="ok")]
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(kwargs["timeout"])
        item = outcomes[len(calls) - 1]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(hc.subprocess, "run", fake_run)
    monkeypatch.setattr(hc.time, "sleep", lambda s: None)
    assert hc._run(["docker", "ps"]) == "ok"
    assert calls == [hc.SUBPROCESS_TIMEOUT, hc.SUBPROCESS_TIMEOUT]
    assert hc.SUBPROCESS_TIMEOUT >= 120


def test_조회가_두_번_모두_실패하면_예외를_올린다(monkeypatch):
    import subprocess

    import pytest

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired("docker", 1)

    monkeypatch.setattr(hc.subprocess, "run", fake_run)
    monkeypatch.setattr(hc.time, "sleep", lambda s: None)
    with pytest.raises(subprocess.TimeoutExpired):
        hc._run(["docker", "ps"])


def test_헬스_체크_자신의_종료_코드_1은_이상으로_보지_않는다():
    jobs = {"health-check": (None, 1), "publish": (None, 0)}
    assert hc.check_launchd(jobs) == []


def test_헬스_체크_자신이_전송_실패나_크래시로_끝나면_이상으로_본다():
    for status in (2, 120, -9):
        found = hc.check_launchd({"health-check": (None, status)})
        assert [f.detail for f in found] == [f"health-check: 마지막 종료 코드 {status}"]


def test_다른_작업의_종료_코드_1은_계속_이상이다():
    found = hc.check_launchd({"backup": (None, 1), "health-check": (None, 1)})
    assert [f.detail for f in found] == ["backup: 마지막 종료 코드 1"]


def test_종료_코드_상수는_서로_다르고_크래시_코드는_자기_정상_범위_밖이다():
    codes = (hc.EXIT_OK, hc.EXIT_ISSUES, hc.EXIT_SEND_FAILED, hc.EXIT_CRASH)
    assert len(set(codes)) == 4
    assert hc.EXIT_CRASH not in hc.SELF_OK_EXITS
    assert hc.SELF_OK_EXITS == (hc.EXIT_OK, hc.EXIT_ISSUES)


def test_자기_종료_코드_경계_0_1은_정상_2와_크래시는_이상이고_타_작업_1은_이상이다():
    def details(jobs):
        return [f.detail for f in hc.check_launchd(jobs)]

    assert details({"health-check": (None, hc.EXIT_OK)}) == []
    assert details({"health-check": (None, hc.EXIT_ISSUES)}) == []
    assert details({"health-check": (None, hc.EXIT_SEND_FAILED)}) == [
        "health-check: 마지막 종료 코드 2"
    ]
    assert details({"health-check": (None, hc.EXIT_CRASH)}) == [
        "health-check: 마지막 종료 코드 3"
    ]
    assert details({"publish": (None, 1)}) == ["publish: 마지막 종료 코드 1"]


def test_처리되지_않은_예외는_크래시_코드로_끝나고_알림에_시크릿이_없다(monkeypatch, caplog):
    secret = "AIza" + "a" * 35
    sent = []

    def boom(argv=None):
        raise RuntimeError(f"HTTPError for url: https://x/y?url=a&key={secret}")

    monkeypatch.setattr(hc, "_run_main", boom)
    monkeypatch.setattr(hc, "send_telegram", lambda text, level: sent.append((text, level)))
    assert hc.main([]) == hc.EXIT_CRASH
    assert len(sent) == 1 and sent[0][1] == "ERROR"
    assert secret not in sent[0][0] and "RuntimeError" in sent[0][0]
    assert secret not in caplog.text and "헬스 체크 자체 오류" in caplog.text


def test_크래시_알림_전송까지_실패해도_크래시_코드를_돌려준다(monkeypatch):
    def boom(argv=None):
        raise ValueError("x")

    def send_fails(text, level):
        raise OSError("network down")

    monkeypatch.setattr(hc, "_run_main", boom)
    monkeypatch.setattr(hc, "send_telegram", send_fails)
    assert hc.main([]) == hc.EXIT_CRASH


def test_정상_실행의_종료_코드는_그대로_전달한다(monkeypatch):
    monkeypatch.setattr(hc, "_run_main", lambda argv=None: hc.EXIT_ISSUES)
    assert hc.main([]) == hc.EXIT_ISSUES


def test_시크릿_마스킹은_키_토큰_쿼리값을_가린다():
    text = (
        "GET https://api/x?url=a&key=AIza" + "b" * 35 + " bot 123456789:" + "c" * 35
        + " token=abc123 password=hunter2"
    )
    masked = hc.mask_secrets(text)
    for leaked in ("AIza", "123456789:", "abc123", "hunter2"):
        assert leaked not in masked
    assert "url=a" in masked


# --- #13 전원·깨우기 예약, #12 최근 백업 시각 -----------------------------------------------------

def _batt(source, pct=None, state="charged"):
    text = f"Now drawing from '{source}'\n"
    if pct is not None:
        text += f" -InternalBattery-0 (id=1)\t{pct}%; {state}; 0:00 remaining present: true\n"
    return text


def test_충전기_연결과_충분한_잔량은_정상이다():
    found = hc.check_power(_batt("AC Power", 100))
    assert [f.level for f in found] == [hc.OK]
    assert "AC" in found[0].detail and "100%" in found[0].detail


def test_배터리로_구동_중이면_잔량이_높아도_오류다():
    found = hc.check_power(_batt("Battery Power", 80, "discharging"))
    assert [f.level for f in found] == [hc.ERROR]
    assert "배터리로 구동" in found[0].detail and "80%" in found[0].detail


def test_배터리_잔량_경계는_30퍼센트다():
    assert hc.BATTERY_LOW_PERCENT == 30
    assert hc.check_power(_batt("AC Power", 30, "charging"))[0].level == hc.OK
    low = hc.check_power(_batt("AC Power", 29, "charging"))
    assert [f.level for f in low] == [hc.WARN]
    assert "29%" in low[0].detail


def test_배터리가_없는_맥은_충전기_연결만_본다():
    assert [f.level for f in hc.check_power(_batt("AC Power"))] == [hc.OK]


def test_전원_출력을_해석하지_못하면_경고한다():
    found = hc.check_power("무슨 말인지 모를 출력")
    assert [f.level for f in found] == [hc.WARN]
    assert "해석" in found[0].detail


_NOW = datetime(2026, 11, 27, 17, 42, tzinfo=hc.KST)


def _sched(*stamps):
    lines = ["Scheduled power events:"]
    for i, stamp in enumerate(stamps):
        lines.append(f" [{i}]  wake at {stamp} by 'pmset'")
    return "\n".join(lines)


def test_다음_01시와_09시_앞에_깨우기가_있으면_정상이다():
    sched = _sched("11/28/2026 00:55:00", "11/28/2026 08:55:00", "11/29/2026 00:55:00")
    found = hc.check_wake_schedule(sched, _NOW)
    assert [f.level for f in found] == [hc.OK]
    assert "11/28 00:55" in found[0].detail


def test_09시_앞_깨우기가_없으면_오류다():
    found = hc.check_wake_schedule(_sched("11/28/2026 00:55:00"), _NOW)
    assert [f.level for f in found] == [hc.ERROR]
    assert "09:00" in found[0].detail and "11/28" in found[0].detail


def test_예약이_하나도_없으면_01시와_09시_둘_다_오류다():
    found = hc.check_wake_schedule("No scheduled events\n", _NOW)
    assert [f.level for f in found] == [hc.ERROR, hc.ERROR]
    assert "01:00" in found[0].detail and "09:00" in found[1].detail


def test_깨우기는_실행_90분_전까지만_인정한다():
    assert hc.WAKE_LEAD_MINUTES == 90
    edge = _sched("11/27/2026 23:30:00", "11/28/2026 07:30:00")  # 정확히 90분 전
    assert [f.level for f in hc.check_wake_schedule(edge, _NOW)] == [hc.OK]
    early = _sched("11/27/2026 23:29:00", "11/28/2026 07:29:00")  # 91분 전
    assert [f.level for f in hc.check_wake_schedule(early, _NOW)] == [hc.ERROR, hc.ERROR]


def test_실행_뒤의_깨우기는_소용없다():
    late = _sched("11/28/2026 01:05:00", "11/28/2026 09:05:00")
    assert [f.level for f in hc.check_wake_schedule(late, _NOW)] == [hc.ERROR, hc.ERROR]


def test_한쪽만_있으면_없는_쪽만_오류로_알린다():
    found = hc.check_wake_schedule(_sched("11/28/2026 07:30:00"), _NOW)
    assert [f.level for f in found] == [hc.ERROR]
    assert found[0].detail.startswith("11/28 01:00")


def test_이미_소비된_당일_깨우기는_오탐하지_않는다():
    now = datetime(2026, 11, 27, 8, 56, tzinfo=hc.KST)  # 08:55 예약은 방금 실행돼 사라졌다
    sched = _sched("11/28/2026 00:55:00", "11/28/2026 08:55:00")
    assert [f.level for f in hc.check_wake_schedule(sched, now)] == [hc.OK]


def test_깨우기_점검은_wake_외_이벤트를_세지_않는다():
    sched = (
        "Scheduled power events:\n"
        " [0]  shutdown at 11/28/2026 00:55:00 by 'pmset'\n"
        " [1]  poweron at 11/28/2026 08:55:00 by 'pmset'\n"
    )
    assert [f.level for f in hc.check_wake_schedule(sched, _NOW)] == [hc.ERROR, hc.ERROR]


def _make_backups(root, n8n=(), sheets=(), partial_sheets=()):
    (root / "n8n").mkdir(parents=True, exist_ok=True)
    (root / "sheets").mkdir(parents=True, exist_ok=True)
    for stamp in n8n:
        (root / "n8n" / f"n8n_{stamp}.tar.gz").write_bytes(b"x")
    for stamp in sheets:
        d = root / "sheets" / stamp
        d.mkdir()
        (d / "manifest.json").write_text("{}")
    for stamp in partial_sheets:
        (root / "sheets" / stamp).mkdir()


_BNOW = datetime(2026, 11, 27, 9, 30, tzinfo=hc.KST)


def test_두_백업이_허용_시간_안이면_정상이다(tmp_path):
    _make_backups(tmp_path, n8n=["20261127_033000"], sheets=["20261127_033000"])
    found = hc.check_backup(tmp_path, _BNOW)
    assert [f.level for f in found] == [hc.OK]
    assert "n8n" in found[0].detail and "Sheets" in found[0].detail


def test_n8n_백업만_오래되면_n8n만_오류다(tmp_path):
    _make_backups(tmp_path, n8n=["20261125_225037"], sheets=["20261127_033000"])
    found = hc.check_backup(tmp_path, _BNOW)
    errors = [f for f in found if f.level == hc.ERROR]
    assert len(errors) == 1 and "n8n" in errors[0].detail
    assert "11/25 22:50" in errors[0].detail and "34시간" in errors[0].detail


def test_백업_허용_시간_경계는_26시간이다(tmp_path):
    assert hc.BACKUP_MAX_AGE_HOURS == 26
    edge = _BNOW - timedelta(hours=26)
    over = _BNOW - timedelta(hours=26, minutes=1)
    _make_backups(tmp_path, n8n=[f"{edge:%Y%m%d_%H%M%S}"], sheets=[f"{edge:%Y%m%d_%H%M%S}"])
    assert [f.level for f in hc.check_backup(tmp_path, _BNOW)] == [hc.OK]
    other = tmp_path / "other"
    _make_backups(other, n8n=[f"{over:%Y%m%d_%H%M%S}"], sheets=[f"{over:%Y%m%d_%H%M%S}"])
    assert [f.level for f in hc.check_backup(other, _BNOW)] == [hc.ERROR, hc.ERROR]


def test_manifest가_없는_미완성_Sheets_스냅샷은_인정하지_않는다(tmp_path):
    _make_backups(
        tmp_path, n8n=["20261127_033000"],
        sheets=["20261125_033000"], partial_sheets=["20261127_033000"],
    )
    errors = [f for f in hc.check_backup(tmp_path, _BNOW) if f.level == hc.ERROR]
    assert len(errors) == 1 and "Sheets" in errors[0].detail and "11/25 03:30" in errors[0].detail


def test_여러_백업_중_가장_최근_것을_본다(tmp_path):
    _make_backups(
        tmp_path,
        n8n=["20261120_033000", "20261127_033000", "20261126_033000"],
        sheets=["20261127_033000", "20261101_033000"],
    )
    assert [f.level for f in hc.check_backup(tmp_path, _BNOW)] == [hc.OK]


def test_백업이_하나도_없으면_둘_다_오류다(tmp_path):
    found = hc.check_backup(tmp_path / "없음", _BNOW)
    assert [f.level for f in found] == [hc.ERROR, hc.ERROR]
    assert all("없음" in f.detail for f in found)


def test_이름_형식이_다른_파일은_무시한다(tmp_path):
    _make_backups(tmp_path, sheets=["20261127_033000"])
    (tmp_path / "n8n" / "memo.txt").write_text("x")
    (tmp_path / "n8n" / "n8n_latest.tar.gz").write_bytes(b"x")
    found = hc.check_backup(tmp_path, _BNOW)
    assert [f.level for f in found] == [hc.ERROR] and "n8n" in found[0].detail


def test_전원_깨우기_조회가_실패하면_경고로_알리고_시크릿은_없다(monkeypatch):
    def fail(cmd):
        raise OSError("pmset 없음 key=SECRETVALUE")

    monkeypatch.setattr(hc, "_run", fail)
    for found in (hc.collect_power(), hc.collect_wake(_NOW)):
        assert [f.level for f in found] == [hc.WARN]
        assert "SECRETVALUE" not in found[0].detail


def test_run_checks가_새_점검_셋을_모두_호출한다(monkeypatch):
    called = []
    for name in ("collect_launchd", "collect_n8n"):
        monkeypatch.setattr(hc, name, lambda *a, _n=name: called.append(_n) or [])
    monkeypatch.setattr(hc, "check_publish_log", lambda *a: [])
    monkeypatch.setattr(hc, "check_log_freshness", lambda *a: [])
    monkeypatch.setattr(hc, "check_lock", lambda *a: [])
    monkeypatch.setattr(hc, "collect_power", lambda: called.append("power") or [])
    monkeypatch.setattr(hc, "collect_wake", lambda now: called.append("wake") or [])
    monkeypatch.setattr(hc, "check_backup", lambda d, now: called.append("backup") or [])
    hc.run_checks(_NOW)
    assert {"power", "wake", "backup"} <= set(called)
