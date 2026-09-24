"""네이버 워크플로우 생성 스크립트 — 티스토리를 복사해 네이버용으로 수정."""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "build_naver_workflow.py"
_spec = importlib.util.spec_from_file_location("build_naver_workflow", _SCRIPT)
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)


@pytest.fixture(scope="module")
def wf() -> dict:
    return builder.build()


def _node(wf: dict, name: str) -> dict:
    matches = [n for n in wf["nodes"] if n["name"] == name]
    assert matches, f"노드 없음: {name}"
    return matches[0]


def _targets(wf: dict, source: str) -> list[str]:
    return [link["node"] for branch in wf["connections"][source]["main"] for link in branch]


def test_네이버_탭을_쓰는_노드(wf):
    for name in builder.TAB_NODES + ["Sheets Read (Naver Published)"]:
        assert _node(wf, name)["parameters"]["sheetName"]["value"] == "naver_calendar"


def test_티스토리_발행_키워드는_티스토리_탭에서_읽는다(wf):
    node = _node(wf, "Sheets Read (Published Keywords)")
    assert node["parameters"]["sheetName"]["value"] == "gid=0"


def test_serpapi_대신_네이버_검색(wf):
    names = {n["name"] for n in wf["nodes"]}
    assert "SerpAPI Search" not in names
    node = _node(wf, "Naver Search (SerpAPI)")
    assert node["parameters"]["url"] == "https://serpapi.com/search.json"
    params = {p["name"]: p["value"] for p in node["parameters"]["queryParameters"]["parameters"]}
    assert params["engine"] == "naver"
    assert params["api_key"] == "={{ $env.SERPAPI_KEY }}"  # 티스토리와 같은 키
    assert node["retryOnFail"] is True and node["maxTries"] == 3
    assert "credentials" not in node


def test_이미지_주입_노드는_없다(wf):
    assert "Inject Images" not in {n["name"] for n in wf["nodes"]}
    assert _targets(wf, "Parse JSON Response") == ["Validate Structure"]
    mapping = _node(wf, "Sheets Update (발행대기)")["parameters"]["columns"]["value"]
    assert "썸네일URL" not in mapping


def test_연결이_모두_존재하는_노드를_가리킨다(wf):
    names = {n["name"] for n in wf["nodes"]}
    for source, outputs in wf["connections"].items():
        assert source in names, source
        for branch in outputs["main"]:
            for link in branch:
                assert link["node"] in names, f"{source} → {link['node']}"


def test_네이버_발행_키워드_조회가_직렬로_끼어든다(wf):
    assert _targets(wf, "Reduce to Trigger") == ["Sheets Read (Naver Published)"]
    assert _targets(wf, "Sheets Read (Naver Published)") == ["Reduce Naver Published"]
    assert _targets(wf, "Reduce Naver Published") == ["Sheets Read (Brain Terms)"]
    # 네이버 탭에 발행 글이 0건이어도 뒤 노드가 실행되게
    assert _node(wf, "Sheets Read (Naver Published)")["alwaysOutputData"] is True


def test_프롬프트가_주입된다(wf):
    route = _node(wf, "Route Prompt (A/B/C)")["parameters"]["jsCode"]
    assert "경험을 지어내지 않습니다" in route
    assert "유형 F: 도구 비교" in route
    assert "'PROMPT_E'" not in route
    verify = _node(wf, "Build Verify Request")["parameters"]["jsCode"]
    assert "no_fabricated_experience" in verify
    assert "'VERIFY_PROMPT' /*END" not in verify


def test_스케줄은_02시_비활성(wf):
    trigger = _node(wf, "Schedule Trigger (02:00 AM)")
    assert trigger["parameters"]["rule"]["interval"][0]["expression"] == "0 2 * * *"
    assert wf["active"] is False


def test_커밋된_파일이_최신이다():
    assert builder.main(["--check"]) == 0


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_주입된_코드가_문법상_유효하다(wf, tmp_path):
    for name in builder.CODE_REPLACEMENTS:
        path = tmp_path / "node.js"
        path.write_text(_node(wf, name)["parameters"]["jsCode"], encoding="utf-8")
        result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, f"{name}: {result.stderr}"


def test_LLM이_고른_카테고리를_시트에_쓴다(wf):
    columns = _node(wf, "Sheets Update (발행대기)")["parameters"]["columns"]["value"]
    assert "Parse JSON Response" in columns["카테고리"]
    assert "category" in columns["카테고리"]
    assert "TechNova" in columns["카테고리"]  # 비어 있으면 기본값
