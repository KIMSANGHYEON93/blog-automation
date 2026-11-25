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
