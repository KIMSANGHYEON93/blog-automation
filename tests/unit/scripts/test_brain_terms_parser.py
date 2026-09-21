"""AI-Brain 용어 카드 파싱 — 볼트 마크다운에서 시트 행 추출."""
import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "sync_brain_terms.py"
_spec = importlib.util.spec_from_file_location("sync_brain_terms", _SCRIPT)
sync = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = sync  # @dataclass가 sys.modules에서 모듈을 찾는다
_spec.loader.exec_module(sync)

CARD = """---
type: term
title: "프롬프트 인젝션"
aliases: ["Prompt Injection", "프롬프트 주입"]
category: 운영평가
level: 4
status: draft
---

# 프롬프트 인젝션 (Prompt Injection)

> **한 줄 정의:** 외부 데이터에 숨겨진 악성 명령이 시스템 프롬프트를 무력화하는 보안 공격.

## 1. 정의

- **정확한 정의:** 직접 주입과 간접 주입으로 나뉜다.
- **비유:** SQL 인젝션.
- **혼동 포인트:** 탈옥(Jailbreak)과 다르다. 탈옥은 안전 가이드라인 우회가 목적이다.

## 3. 관련 개념

- 상위: [가드레일](가드레일.md)

## 6. 출처

- 원문: [OWASP Top 10 for LLM (LLM01)](https://owasp.org/llm-top10)
- 참고: 시드 정의
"""

SEED_CARD = """---
type: term
title: "임베딩"
aliases: []
status: seed
---

# 임베딩

> **한 줄 정의:** 텍스트를 숫자 벡터로 바꾸는 것.

## 6. 출처

- 원문: (공식 문서/논문 링크 추가)
"""


class TestParseTermCard:
    def test_주요_필드_추출(self):
        term = sync.parse_term_card(CARD, filename="프롬프트인젝션.md")
        assert term.name == "프롬프트 인젝션"
        assert term.aliases == "Prompt Injection, 프롬프트 주입"
        assert "악성 명령" in term.definition
        assert term.definition.endswith("보안 공격.")
        assert "탈옥" in term.confusion
        assert term.source == "OWASP Top 10 for LLM (LLM01)"

    def test_별칭_출처_없는_카드(self):
        term = sync.parse_term_card(SEED_CARD, filename="임베딩.md")
        assert term.name == "임베딩"
        assert term.aliases == ""
        assert term.definition == "텍스트를 숫자 벡터로 바꾸는 것."
        assert term.confusion == ""
        assert term.source == ""  # 플레이스홀더는 출처로 보지 않음

    def test_제목이_없으면_파일명_사용(self):
        term = sync.parse_term_card("> **한 줄 정의:** 설명.", filename="하네스.md")
        assert term.name == "하네스"

    def test_한줄정의_없으면_None(self):
        assert sync.parse_term_card("# 제목만 있음", filename="x.md") is None

    def test_드라이브_이스케이프_마크다운_처리(self):
        # Drive 내보내기가 \\--- 나 \\# 처럼 이스케이프하는 경우
        escaped = CARD.replace("---", "\\---").replace("# 프롬프트", "\\# 프롬프트")
        term = sync.parse_term_card(escaped, filename="프롬프트인젝션.md")
        assert term is not None
        assert term.name == "프롬프트 인젝션"


class TestToRow:
    def test_시트_행_순서(self):
        term = sync.parse_term_card(CARD, filename="프롬프트인젝션.md")
        assert term.to_row()[:2] == ["프롬프트 인젝션", "Prompt Injection, 프롬프트 주입"]
        assert len(term.to_row()) == 5
