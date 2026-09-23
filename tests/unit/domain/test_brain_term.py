"""BrainTerm — AI-Brain 볼트 용어 카드 값 객체 + 키워드 생성 규칙.

GSC는 '이미 노출된 쿼리'만 반환해서 트래픽 없는 주제는 영원히 발굴되지 않는다
(트래픽 없음 → 키워드 없음 → 글 없음 → 트래픽 없음). 볼트 용어 381건은
트래픽과 무관한 시드다. 용어 카드에서 직접 키워드를 만들어 루프를 끊는다.

'혼동포인트'는 `A ≠ B. 설명...` 형식으로 376/381건(98%)이 채워져 있어
비교 글 주제를 그대로 제공한다.
"""
from __future__ import annotations

import dataclasses

import pytest

from src.domain.value_objects.brain_term import BrainTerm


class TestBrainTermBasics:
    def test_용어와_정의로_만든다(self):
        t = BrainTerm(name="MCP", definition="모델과 도구를 잇는 개방형 프로토콜")
        assert t.name == "MCP"
        assert t.aliases == ()

    def test_불변이다(self):
        t = BrainTerm(name="MCP", definition="정의")
        with pytest.raises(dataclasses.FrozenInstanceError):
            t.name = "다른것"  # type: ignore[misc]

    def test_용어가_비면_거부한다(self):
        with pytest.raises(ValueError):
            BrainTerm(name="  ", definition="정의")

    def test_앞뒤_공백은_정리된다(self):
        t = BrainTerm(name="  MCP  ", definition="  정의  ")
        assert t.name == "MCP"
        assert t.definition == "정의"


class TestAliases:
    def test_쉼표로_구분된_별칭을_나눈다(self):
        t = BrainTerm(name="MCP", definition="d",
                      aliases_raw="Model Context Protocol, MCP 서버")
        assert t.aliases == ("Model Context Protocol", "MCP 서버")

    def test_빈_조각과_한_글자는_버린다(self):
        t = BrainTerm(name="MCP", definition="d", aliases_raw="A, , Model Context Protocol,  ")
        assert t.aliases == ("Model Context Protocol",)

    def test_별칭이_없으면_빈_튜플(self):
        assert BrainTerm(name="MCP", definition="d", aliases_raw="").aliases == ()


class TestConfusionTarget:
    """`A ≠ B. 설명` 에서 B를 뽑는다."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("MCP ≠ 에이전트. 에이전트는 판단하고...", "에이전트"),
            ("LLM ≠ 챗봇", "챗봇"),
            ("4D 내부 루프 ≠ 4D 외부 루프. 외부 루프가...", "4D 외부 루프"),
            # 마크다운 링크는 표시 텍스트만 남긴다
            ("A ≠ [프롬프트 엔지니어링](프롬프트.md). 설명", "프롬프트 엔지니어링"),
            # 괄호 영문 병기는 떼어낸다 — 검색어로 쓰기 어렵다
            ("A ≠ 비판적 감식(Discernment). 설명", "비판적 감식"),
            # 백틱은 떼되 값은 살린다 — "CLAUDE.md vs README 차이"는 쓸 만하다
            ("CLAUDE.md ≠ `README", "README"),
        ],
    )
    def test_대상을_뽑는다(self, raw, expected):
        t = BrainTerm(name="A", definition="d", confusion_raw=raw)
        assert t.confusion_target() == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "특별히 혼동할 대상이 없다",
            # '단순~'은 서술형이라 검색어가 못 된다
            "A ≠ 단순 프롬프트 엔지니어링 기법. 설명",
            "A ≠ 단순 관리자 결재 승인. 설명",
            # 너무 길면 검색어가 아니다
            "A ≠ " + "가" * 40,
            # 다중 부등호는 대상이 하나로 안 잡힌다: "토큰 ≠ 단어 ≠ 글자"
            "토큰 ≠ 단어 ≠ 글자. 설명",
            # 슬래시로 묶인 병렬 개념은 검색어가 못 된다
            "A ≠ 툴 유즈 / 함수 호출. 설명",
        ],
    )
    def test_비교에_못_쓰는_대상은_None(self, raw):
        t = BrainTerm(name="A", definition="d", confusion_raw=raw)
        assert t.confusion_target() is None


class TestKeywordCandidates:
    def test_정의형_키워드는_항상_나온다(self):
        t = BrainTerm(name="MCP", definition="d")
        assert "MCP란" in t.keyword_candidates()

    def test_혼동_대상이_있으면_비교형도_나온다(self):
        t = BrainTerm(name="MCP", definition="d", confusion_raw="MCP ≠ 에이전트. 설명")
        kws = t.keyword_candidates()
        assert "MCP란" in kws
        assert "MCP vs 에이전트 차이" in kws

    def test_혼동_대상이_없으면_정의형만(self):
        t = BrainTerm(name="MCP", definition="d", confusion_raw="없음")
        assert t.keyword_candidates() == ("MCP란",)

    def test_대상이_자기_자신이면_비교형을_안_만든다(self):
        t = BrainTerm(name="MCP", definition="d", confusion_raw="MCP ≠ MCP. 설명")
        assert t.keyword_candidates() == ("MCP란",)

    def test_순서는_정의형이_먼저다(self):
        """정의형이 비교형보다 검색 의도가 넓다."""
        t = BrainTerm(name="MCP", definition="d", confusion_raw="MCP ≠ 에이전트.")
        assert t.keyword_candidates()[0] == "MCP란"


class TestParticle:
    """'LLM란'이 아니라 'LLM이란' — 조사는 korean_particle 규칙을 따른다."""

    @pytest.mark.parametrize(
        ("name", "expected"),
        [("LLM", "LLM이란"), ("MCP", "MCP란"),
         ("HHH 원칙", "HHH 원칙이란"), ("에이전트", "에이전트란")],
    )
    def test_정의형_조사(self, name, expected):
        t = BrainTerm(name=name, definition="d")
        assert t.keyword_candidates()[0] == expected


class TestPriority:
    """검색량 대용 지표 — 짧고, 별칭이 많고, 출처가 있는 용어가 널리 쓰인다."""

    def test_짧은_용어가_더_높다(self):
        short = BrainTerm(name="MCP", definition="d")
        long = BrainTerm(name="계층형 에이전트 라우팅", definition="d")
        assert short.priority() > long.priority()

    def test_별칭이_많으면_더_높다(self):
        few = BrainTerm(name="MCP", definition="d", aliases_raw="")
        many = BrainTerm(name="MCP", definition="d",
                         aliases_raw="Model Context Protocol, MCP 서버, 엠씨피")
        assert many.priority() > few.priority()

    def test_출처가_있으면_더_높다(self):
        no_src = BrainTerm(name="MCP", definition="d")
        with_src = BrainTerm(name="MCP", definition="d", source="spec.md")
        assert with_src.priority() > no_src.priority()
