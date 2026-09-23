"""한국어 조사 선택 — 받침 있으면 '이란', 없으면 '란'.

'LLM란', 'HHH 원칙란'처럼 틀린 조사는 검색어로도 어색하고 제목 품질도 떨어뜨린다.
영문 약어는 한국어 발음의 끝소리로 판정해야 한다(LLM=엘엘엠 → 받침 ㅁ).
"""
from __future__ import annotations

import pytest

from src.domain.services.korean_particle import has_final_consonant, with_iran


class TestHangulFinalConsonant:
    @pytest.mark.parametrize(
        ("word", "expected"),
        [
            ("원칙", True),    # 칙 → ㄱ
            ("스케줄링", True),  # 링 → ㅇ
            ("에이전트", False),  # 트 → 받침 없음
            ("프레임워크", False),  # 크 → 받침 없음
            ("가드레일", True),   # 일 → ㄹ
            ("챗봇", True),     # 봇 → ㅅ
        ],
    )
    def test_한글_받침_판정(self, word, expected):
        assert has_final_consonant(word) is expected


class TestLatinFinalConsonant:
    """영문 약어는 한국어 읽기의 끝소리로 본다."""

    @pytest.mark.parametrize(
        ("word", "expected"),
        [
            ("LLM", True),    # 엘엘엠 → ㅁ
            ("RAG", False),   # 래그 → 받침 없음
            ("MCP", False),   # 엠씨피 → 없음
            ("API", False),   # 에이피아이 → 없음
            ("DAG", False),   # 디에이지 → 없음
            ("SQL", True),    # 에스큐엘 → ㄹ
            ("CDN", True),    # 씨디엔 → ㄴ
        ],
    )
    def test_영문_약어_받침_판정(self, word, expected):
        assert has_final_consonant(word) is expected

    def test_소문자도_같게_본다(self):
        assert has_final_consonant("llm") is True


class TestDigits:
    @pytest.mark.parametrize(
        ("word", "expected"),
        [("1", False), ("3", True), ("6", True), ("7", True), ("10", True), ("8", False)],
    )
    def test_숫자_끝(self, word, expected):
        """10은 마지막 글자 0(영)으로 판정돼 '10이란'이 된다 — '십'과도 일치한다."""
        assert has_final_consonant(word) is expected


class TestWithIran:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("LLM", "LLM이란"),
            ("MCP", "MCP란"),
            ("HHH 원칙", "HHH 원칙이란"),
            ("DAG 스케줄링", "DAG 스케줄링이란"),
            ("4D 프레임워크", "4D 프레임워크란"),
            ("에이전트", "에이전트란"),
        ],
    )
    def test_조사를_붙인다(self, name, expected):
        assert with_iran(name) == expected

    def test_괄호나_기호로_끝나면_직전_글자로_판정(self):
        assert with_iran("가드레일(Guardrail)") == "가드레일(Guardrail)이란"

    def test_빈_문자열은_그대로(self):
        assert with_iran("") == ""
