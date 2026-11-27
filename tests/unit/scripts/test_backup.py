"""백업 스크립트 — 보관 정리·파일 이름·스냅샷 형식·내보내기 검증(외부 호출 없음)."""
import csv
import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "backup.py"
_spec = importlib.util.spec_from_file_location("backup", _SCRIPT)
bk = importlib.util.module_from_spec(_spec)
sys.modules["backup"] = bk
_spec.loader.exec_module(bk)


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_탭_이름의_경로_문자는_바뀌고_한글은_유지된다():
    assert bk.safe_name("naver_calendar") == "naver_calendar"
    assert bk.safe_name("AI브레인용어") == "AI브레인용어"
    assert bk.safe_name("a/b\\c:d") == "a_b_c_d"
    assert bk.safe_name("..") == "_"


def test_보관_개수를_넘는_오래된_항목만_지운다(tmp_path):
    for stamp in ("20261101_000000", "20261102_000000", "20261103_000000", "20261104_000000"):
        (tmp_path / f"n8n_{stamp}.tar.gz").write_text("x")
    (tmp_path / "other.txt").write_text("keep me")
    removed = bk.prune(tmp_path, "n8n_", keep=2)
    assert [p.name for p in removed] == ["n8n_20261101_000000.tar.gz", "n8n_20261102_000000.tar.gz"]
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ["n8n_20261103_000000.tar.gz", "n8n_20261104_000000.tar.gz", "other.txt"]


def test_디렉터리도_정리한다(tmp_path):
    for stamp in ("20261101_000000", "20261102_000000"):
        (tmp_path / stamp).mkdir()
        (tmp_path / stamp / "a.csv").write_text("x")
    bk.prune(tmp_path, "20", keep=1)
    assert [p.name for p in tmp_path.iterdir()] == ["20261102_000000"]


def test_없는_디렉터리는_정리할_것이_없다(tmp_path):
    assert bk.prune(tmp_path / "none", "n8n_", keep=7) == []


def test_스냅샷은_탭별_csv와_manifest를_600으로_만든다(tmp_path):
    tabs = {"탭 1": [["a", "b"], ["1", "한글, 쉼표"]], "빈 탭": []}
    target = tmp_path / "20261125_090000"
    manifest = bk.write_sheet_snapshot(target, tabs)
    assert manifest == {"탭 1": {"rows": 2, "cols": 2}, "빈 탭": {"rows": 0, "cols": 0}}
    with open(target / "탭 1.csv", newline="", encoding="utf-8") as fh:
        assert list(csv.reader(fh)) == tabs["탭 1"]
    assert json.loads((target / "manifest.json").read_text(encoding="utf-8")) == manifest
    assert _mode(target) == 0o700
    assert _mode(target / "탭 1.csv") == 0o600
    assert _mode(target / "manifest.json") == 0o600


def test_워크플로_내보내기가_비었거나_깨졌으면_실패한다():
    assert bk.validate_workflows('[{"id": "a"}, {"id": "b"}]') == 2
    with pytest.raises(ValueError):
        bk.validate_workflows("[]")
    with pytest.raises(ValueError):
        bk.validate_workflows("{}")
    with pytest.raises(json.JSONDecodeError):
        bk.validate_workflows("not json")


def _docker_inspect(monkeypatch, results):
    """results: 호출마다 돌려줄 값(예외면 던진다). 대기 시간은 없앤다."""
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        item = results[len(calls) - 1]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(bk, "_run", fake_run)
    monkeypatch.setattr(bk.time, "sleep", lambda s: None)
    return calls


def test_컨테이너_조회가_일시_실패해도_재시도해서_실행_중이면_통과한다(monkeypatch):
    import subprocess

    calls = _docker_inspect(
        monkeypatch, [subprocess.TimeoutExpired("docker", 1), "running\n"]
    )
    assert bk.container_running() is True
    assert len(calls) == 2


def test_컨테이너_조회가_계속_실패하면_정해진_횟수만_시도하고_거짓이다(monkeypatch):
    import subprocess

    err = subprocess.CalledProcessError(1, "docker")
    calls = _docker_inspect(monkeypatch, [err] * bk.CONTAINER_CHECK_TRIES)
    assert bk.container_running() is False
    assert len(calls) == bk.CONTAINER_CHECK_TRIES


def test_컨테이너가_멈춰_있으면_재시도하지_않고_거짓이다(monkeypatch):
    calls = _docker_inspect(monkeypatch, ["exited\n"])
    assert bk.container_running() is False
    assert len(calls) == 1
