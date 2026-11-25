"""경험 문단 빠른 입력 — 질문 읽기·문단 조립·표시 바꾸기 (LLM 없이 템플릿만)."""
import pytest

from src.domain.services.experience_note import (
    FALLBACK_QUESTION,
    ExperienceInputError,
    ExperienceResult,
    compose_experience_paragraph,
    experience_questions,
    fill_experience,
)

NEW_FORMAT = (
    "[[직접 해 보니]] 이 글의 방법을 실제로 해 보고 아래 질문에 답해 주세요. "
    "확인할 것: 무료 요금제로 회의록 요약이 됐나요? 몇 분 분량까지 됐나요?"
)
LEGACY = (
    "[[직접 해 보니]] 이 글의 방법을 실제로 해 본 결과를 2~3문장으로 적고 화면 캡처를 넣어 "
    "주세요. 확인할 것: 무료 요금제에서 회의록 요약이 몇 분 분량까지 되는지, 화자 구분이 맞는지"
)


def _body(marker_line: str) -> str:
    return f"## 설정\n\n설명 문단.\n\n{marker_line}\n\n## 자주 묻는 질문\n\nQ. 무료인가요?"


class TestExperienceQuestions:
    def test_물음표로_끝나는_질문을_하나씩_나눈다(self):
        assert experience_questions(_body(NEW_FORMAT)) == [
            "무료 요금제로 회의록 요약이 됐나요?", "몇 분 분량까지 됐나요?",
        ]

    def test_슬래시나_쉼표로_이어_써도_나눈다(self):
        line = "[[직접 해 보니]] 확인할 것: 요약이 됐나요? / 화자 구분이 맞았나요?"
        assert experience_questions(line) == ["요약이 됐나요?", "화자 구분이 맞았나요?"]

    def test_예전_자유_형식은_통째로_한_질문으로_본다(self):
        assert experience_questions(_body(LEGACY)) == [
            "무료 요금제에서 회의록 요약이 몇 분 분량까지 되는지, 화자 구분이 맞는지",
        ]

    def test_확인할_것이_없으면_기본_질문_하나(self):
        assert experience_questions("[[직접 해 보니]] 해 보고 적어 주세요.") == [FALLBACK_QUESTION]

    def test_표시가_없으면_빈_목록(self):
        assert experience_questions("본문만 있다.") == []

    def test_질문은_세_개까지만(self):
        line = "[[직접 해 보니]] 확인할 것: 가가? 나나? 다다? 라라?"
        assert experience_questions(line) == ["가가?", "나나?", "다다?"]


class TestComposeParagraph:
    QA = [("무료 요금제로 회의록 요약이 됐나요?", "예"), ("몇 분 분량까지 됐나요?", "30분")]

    def test_결과와_답을_1인칭_사실문으로_조립한다(self):
        text = compose_experience_paragraph(ExperienceResult.PARTIAL, self.QA, "")
        assert text == (
            "이 글의 방법을 제가 직접 해 봤고, 일부만 됐습니다.\n\n"
            "- 무료 요금제로 회의록 요약이 됐나요? → 예\n"
            "- 몇 분 분량까지 됐나요? → 30분"
        )

    @pytest.mark.parametrize("result, sentence", [
        (ExperienceResult.WORKED, "이 글의 방법을 제가 직접 해 봤고, 그대로 됐습니다."),
        (ExperienceResult.FAILED, "이 글의 방법을 제가 직접 해 봤지만, 그대로는 되지 않았습니다."),
    ])
    def test_결과마다_첫_문장이_다르다(self, result, sentence):
        assert compose_experience_paragraph(result, self.QA, "").startswith(sentence)

    def test_메모는_첫_문단_끝에_입력_그대로_붙인다(self):
        text = compose_experience_paragraph(
            ExperienceResult.WORKED, self.QA, "  화자가 3명이면\n 섞였습니다. ",
        )
        assert text.splitlines()[0] == (
            "이 글의 방법을 제가 직접 해 봤고, 그대로 됐습니다. 화자가 3명이면 섞였습니다."
        )

    def test_입력에_없는_수치나_문장을_만들지_않는다(self):
        text = compose_experience_paragraph(ExperienceResult.WORKED, [("됐나요?", "예")], "")
        assert text == "이 글의 방법을 제가 직접 해 봤고, 그대로 됐습니다.\n\n- 됐나요? → 예"

    def test_결과가_없으면_거절한다(self):
        with pytest.raises(ExperienceInputError, match="결과"):
            compose_experience_paragraph(None, self.QA, "")

    def test_빈_답이_하나라도_있으면_거절한다(self):
        with pytest.raises(ExperienceInputError, match="답"):
            compose_experience_paragraph(ExperienceResult.WORKED, [("됐나요?", "  ")], "")

    def test_질문이_없으면_거절한다(self):
        with pytest.raises(ExperienceInputError):
            compose_experience_paragraph(ExperienceResult.WORKED, [], "")

    def test_너무_긴_답은_거절한다(self):
        with pytest.raises(ExperienceInputError, match="짧게"):
            compose_experience_paragraph(ExperienceResult.WORKED, [("됐나요?", "가" * 61)], "")

    def test_너무_긴_메모는_거절한다(self):
        with pytest.raises(ExperienceInputError, match="메모"):
            compose_experience_paragraph(ExperienceResult.WORKED, [("됐나요?", "예")], "가" * 121)

    @pytest.mark.parametrize("bad", ["[[직접 해 보니]]", "[[사진:a.jpg]]", "<!-- 사진: x -->"])
    def test_표시_문법은_넣을_수_없다(self, bad):
        with pytest.raises(ExperienceInputError):
            compose_experience_paragraph(ExperienceResult.WORKED, [("됐나요?", bad)], "")
        with pytest.raises(ExperienceInputError):
            compose_experience_paragraph(ExperienceResult.WORKED, [("됐나요?", "예")], bad)


class TestFillExperience:
    def test_표시_줄만_조립한_문단으로_바꾼다(self):
        body = _body(NEW_FORMAT)
        filled = fill_experience(body, "제가 해 봤습니다.\n\n- 됐나요? → 예")
        assert filled == (
            "## 설정\n\n설명 문단.\n\n제가 해 봤습니다.\n\n- 됐나요? → 예\n\n"
            "## 자주 묻는 질문\n\nQ. 무료인가요?"
        )
        assert "[[직접 해 보니]]" not in filled

    def test_표시가_없으면_거절한다(self):
        with pytest.raises(ExperienceInputError, match="이미"):
            fill_experience("본문만 있다.", "문단")

    def test_결과를_문자열로_고른다(self):
        assert ExperienceResult.from_form("partial") is ExperienceResult.PARTIAL
        assert ExperienceResult.from_form("") is None
        assert ExperienceResult.from_form("hack") is None
