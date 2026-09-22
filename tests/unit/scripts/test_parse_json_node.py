"""n8n parse_json.js — 3차 폴백이 이스케이프를 되돌리는지 검증.

2026-09-22: LLM 응답의 JSON 문자열 안에 원시 개행이 들어와 1·2차 파싱이 실패하고,
3차 폴백이 raw 문자열을 그대로 저장해 본문에 리터럴 \\n 이 196개 남았다
(발행글 539·540의 양식 깨짐 원인). 마크다운 변환기가 문단·헤딩을 인식하지 못한다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "n8n" / "code_nodes" / "parse_json.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node 필요")

HARNESS = """
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const raw = fs.readFileSync(process.argv[3], 'utf8');
const fn = new Function('$input', '$', src);
const out = fn({ item: { json: { text: raw } } },
               () => ({ item: { json: { prompt_type: 'A' } } }));
process.stdout.write(JSON.stringify(out.json));
"""


def run_parse(tmp_path: Path, llm_text: str) -> dict:
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    raw_file = tmp_path / "raw.txt"
    raw_file.write_text(llm_text, encoding="utf-8")
    proc = subprocess.run(
        ["node", str(harness), str(SCRIPT), str(raw_file)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"node 실행 실패:\n{proc.stderr[:600]}"
    return json.loads(proc.stdout)


_FAQ_ANSWER = (
    "테스트용 FAQ 답변입니다. parse_json.js의 FAQ 검증 로직은 답변이 최소 80자 이상이어야 "
    "통과시키므로, 이 문장은 그 기준을 넉넉히 넘도록 작성했으며 "
    "플레이스홀더 표현도 쓰지 않았습니다."
)


def _response(body: str) -> str:
    """LLM이 코드펜스로 감싸고 content 안에 원시 개행을 넣은 응답 (1·2차 파싱 실패 유발)."""
    return (
        "```json\n{\n"
        '  "title": "테스트 제목",\n'
        '  "meta_description": "테스트 메타 설명입니다. 충분히 길게 작성한 설명 문장입니다.",\n'
        f'  "content": "{body}",\n'
        f'  "faq_schema": [{{"question": "테스트 질문인가요?", "answer": "{_FAQ_ANSWER}"}}],\n'
        '  "references": ["https://example.com/reference-doc"],\n'
        '  "internal_link_keywords": ["테스트"]\n'
        "}\n```"
    )


def _long(text: str) -> str:
    """본문 최소 길이(1,500자) 검증을 통과하도록 채운다."""
    filler = "실무 적용 관점에서 살펴본 상세 설명 문장입니다. " * 60
    return f"{text}\\n\\n{filler}"


class TestBoundaryFallbackUnescape:
    def test_리터럴_개행이_실제_개행으로_복원(self, tmp_path):
        body = _long("## 제목\\n\\n본문 문단입니다.\\n\\n### 소제목\\n- 항목 하나\n원시 개행 포함")
        result = run_parse(tmp_path, _response(body))
        content = result["content"]
        assert "\\n" not in content, f"리터럴 개행이 남음: {content[:120]}"
        assert content.count("\n") >= 4
        assert content.startswith("## 제목")

    def test_이스케이프된_따옴표_복원(self, tmp_path):
        body = _long('그는 \\"이전 지시를 무시하라\\"고 말했다.\\n다음 줄.\n원시 개행')
        content = run_parse(tmp_path, _response(body))["content"]
        assert '\\"' not in content
        assert '"이전 지시를 무시하라"' in content

    def test_정상_JSON은_그대로_파싱(self, tmp_path):
        body = _long("## 제목\\n\\n본문.")
        content = run_parse(tmp_path, _response(body))["content"]
        assert content.startswith("## 제목\n\n본문.")
        assert "\\n" not in content


class TestRealBrokenResponse:
    """실제 실패 사례 (2026-09-22 발행글 539·540).

    본문 YAML 코드블록에 원시 개행이 섞여 1·2차 파싱이 모두 실패하고
    3차 폴백까지 내려간 응답이다.
    """

    FIXTURE = ROOT / "tests" / "fixtures" / "llm_response_broken.txt"

    def test_3차_폴백에서도_마크다운_구조_보존(self, tmp_path):
        result = run_parse(tmp_path, self.FIXTURE.read_text(encoding="utf-8"))
        content = result["content"]
        assert "\\n" not in content, f"리터럴 개행 {content.count(chr(92) + 'n')}개 남음"
        assert '\\"' not in content, "리터럴 이스케이프 따옴표가 남음"
        assert content.count("\n") > 100, "실제 개행이 거의 없음 — 한 덩어리로 렌더링됨"
        assert content.count("## ") >= 5, "헤딩이 마크다운으로 인식되지 않음"
