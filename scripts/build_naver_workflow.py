"""n8n/workflow_complete.json(티스토리) → n8n/workflow_naver.json(네이버) 생성.

네이버 워크플로우를 손으로 복사·수정하지 않는다.
노드 코드는 n8n/code_nodes/naver/*.js, 프롬프트는
n8n/prompts/prompt_naver_*.md 가 원본이고 이 스크립트가 JSON에 넣는다.
jsCode를 손으로 붙여넣다 줄바꿈이 이중 이스케이프되는 사고(CLAUDE.md)를
막기 위해서다.

    python scripts/build_naver_workflow.py          # 생성
    python scripts/build_naver_workflow.py --check  # 커밋된 파일이 최신인지
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N8N_DIR = ROOT / "n8n"
BASE = N8N_DIR / "workflow_complete.json"
OUTPUT = N8N_DIR / "workflow_naver.json"
CODE_DIR = N8N_DIR / "code_nodes" / "naver"
PROMPT_DIR = N8N_DIR / "prompts"

NAVER_TAB = "naver_calendar"
WORKFLOW_NAME = "Blog Automation Pipeline A — Naver"
OLD_TRIGGER = "Schedule Trigger (01:00 AM)"
NEW_TRIGGER = "Schedule Trigger (02:00 AM)"
SCHEDULE_CRON = "0 2 * * *"  # 티스토리(01:00)와 LLM 호출 시간이 겹치지 않게

TAB_NODES = [
    "Sheets Read (Status=대기)",
    "Sheets Update (발행대기)",
    "Sheets Update (검수필요)",
    "Sheets Update (중복스킵)",
]
CODE_REPLACEMENTS = {
    "Parse SERP Data": "parse_naver_search.js",
    "Route Prompt (A/B/C)": "route_prompt_naver.js",
    "Validate Structure": "validate_structure_naver.js",
    "Build Verify Request": "build_verify_request_naver.js",
    "Parse Verification Result": "parse_verification_naver.js",
    "Check Duplicate": "check_duplicate_naver.js",
}
PROMPT_FILES = {
    "E": "prompt_naver_e_howto.md",
    "F": "prompt_naver_f_compare.md",
    "G": "prompt_naver_g_explain.md",
}
COMMON_PROMPT = "prompt_naver_common.md"
VERIFY_PROMPT = "prompt_naver_h_verification.md"

REDUCE_NAVER_CODE = (
    "// 네이버 발행 키워드 N건을 1건으로 축약\n"
    "// 키워드는 Check Duplicate에서"
    " $('Sheets Read (Naver Published)')로 참조\n"
    "return [{ json: { naver_published_loaded: $input.all().length } }];"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _node(wf: dict, name: str) -> dict:
    for node in wf["nodes"]:
        if node["name"] == name:
            return node
    raise KeyError(f"워크플로우에 노드 없음: {name}")


def _link(name: str) -> dict:
    return {"node": name, "type": "main", "index": 0}


def _rename(wf: dict, old: str, new: str) -> None:
    _node(wf, old)["name"] = new
    conns = wf["connections"]
    if old in conns:
        conns[new] = conns.pop(old)
    for outputs in conns.values():
        for branch in outputs.get("main", []):
            for link in branch:
                if link["node"] == old:
                    link["node"] = new


def _inject(code: str, marker: str, value: object) -> str:
    pattern = re.compile(rf"/\*INJECT:{marker}\*/.*?/\*END:{marker}\*/", re.S)
    if not pattern.search(code):
        raise ValueError(f"주입 표식 없음: {marker}")
    literal = json.dumps(value, ensure_ascii=False)
    return pattern.sub(lambda _: f"/*INJECT:{marker}*/ {literal} /*END:{marker}*/", code)


def _prompts() -> dict[str, str]:
    common = _read(PROMPT_DIR / COMMON_PROMPT).strip()
    return {
        key: f"{common}\n\n{_read(PROMPT_DIR / name).strip()}"
        for key, name in PROMPT_FILES.items()
    }


def _node_code(filename: str) -> str:
    code = _read(CODE_DIR / filename)
    if filename == "route_prompt_naver.js":
        code = _inject(code, "PROMPTS", _prompts())
    if filename == "build_verify_request_naver.js":
        code = _inject(code, "VERIFY_PROMPT", _read(PROMPT_DIR / VERIFY_PROMPT).strip())
    return code


def _use_naver_tab(node: dict) -> None:
    node["parameters"]["sheetName"] = {"__rl": True, "value": NAVER_TAB, "mode": "name"}


def _replace_serp_with_naver_search(wf: dict) -> None:
    _rename(wf, "SerpAPI Search", "Naver Blog Search")
    node = _node(wf, "Naver Blog Search")
    node["id"] = "naver-blog-search"
    node["parameters"] = {
        "method": "GET",
        "url": "https://openapi.naver.com/v1/search/blog.json",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpCustomAuth",
        "sendQuery": True,
        "queryParameters": {"parameters": [
            {"name": "query", "value": "={{ $json['키워드'] }}"},
            {"name": "display", "value": "5"},
            {"name": "sort", "value": "sim"},
        ]},
        "options": {},
    }
    # 두 헤더(X-Naver-Client-Id/Secret)가 필요해 Header Auth 대신 Custom Auth
    # 키를 $env로 넣으면 실행 기록에 평문으로 남는다.
    node["credentials"] = {
        "httpCustomAuth": {
            "id": "naverSearchCustomAuth01",
            "name": "Naver Search API (Custom Auth)",
        },
    }
    node["retryOnFail"] = True
    node["maxTries"] = 3
    node["waitBetweenTries"] = 2000


def _drop_image_injection(wf: dict) -> None:
    # 외부 이미지 URL 붙여넣기는 네이버 검증 전(텍스트만 1단계)
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] != "Inject Images"]
    wf["connections"].pop("Inject Images", None)
    wf["connections"]["Parse JSON Response"] = {"main": [[_link("Validate Structure")]]}
    target = _node(wf, "Sheets Update (발행대기)")["parameters"]["columns"]["value"]
    target.pop("썸네일URL", None)


def _add_naver_published_read(wf: dict) -> None:
    tistory_read = _node(wf, "Sheets Read (Published Keywords)")
    naver_read = copy.deepcopy(tistory_read)
    naver_read["name"] = "Sheets Read (Naver Published)"
    naver_read["id"] = "naver-published-read"
    # 네이버 발행 글이 0건이어도 뒤 노드가 실행되게
    naver_read["alwaysOutputData"] = True
    naver_read["position"] = [tistory_read["position"][0], tistory_read["position"][1] + 440]
    _use_naver_tab(naver_read)

    reduce_node = copy.deepcopy(_node(wf, "Reduce to Trigger"))
    reduce_node["name"] = "Reduce Naver Published"
    reduce_node["id"] = "reduce-naver-published"
    reduce_node["parameters"]["jsCode"] = REDUCE_NAVER_CODE
    reduce_node["position"] = [reduce_node["position"][0], reduce_node["position"][1] + 440]

    wf["nodes"] += [naver_read, reduce_node]
    # n8n은 병렬 브랜치 순서를 보장하지 않으므로 직렬로 끼운다 (CLAUDE.md)
    conns = wf["connections"]
    conns["Reduce to Trigger"] = {"main": [[_link("Sheets Read (Naver Published)")]]}
    conns["Sheets Read (Naver Published)"] = {"main": [[_link("Reduce Naver Published")]]}
    conns["Reduce Naver Published"] = {"main": [[_link("Sheets Read (Brain Terms)")]]}


def build() -> dict:
    wf = json.loads(_read(BASE))
    for name in TAB_NODES:
        _use_naver_tab(_node(wf, name))
    _replace_serp_with_naver_search(wf)
    _drop_image_injection(wf)
    _add_naver_published_read(wf)
    for name, filename in CODE_REPLACEMENTS.items():
        _node(wf, name)["parameters"]["jsCode"] = _node_code(filename)
    _rename(wf, OLD_TRIGGER, NEW_TRIGGER)
    _node(wf, NEW_TRIGGER)["parameters"]["rule"] = {
        "interval": [{"field": "cronExpression", "expression": SCHEDULE_CRON}],
    }
    return {
        "name": WORKFLOW_NAME,
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings") or {},
        "pinData": {},
        "meta": wf.get("meta") or {},
        "active": False,  # 가져온 뒤 수동 실행으로 검증하고 사람이 켠다
        "tags": [],
    }


def render(workflow: dict) -> str:
    return json.dumps(workflow, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="네이버 n8n 워크플로우 생성")
    parser.add_argument(
        "--check", action="store_true", help="커밋된 파일이 최신인지 확인"
    )
    args = parser.parse_args(argv)

    text = render(build())
    if args.check:
        if not OUTPUT.exists() or _read(OUTPUT) != text:
            msg = "n8n/workflow_naver.json이 최신이 아님"
            print(f"{msg} — python scripts/build_naver_workflow.py 실행")
            return 1
        print("n8n/workflow_naver.json 최신")
        return 0
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"생성: {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
