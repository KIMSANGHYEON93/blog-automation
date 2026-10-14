"""AI 티 점검 — humanize-korean 룰북(quick-rules)에서 결정적으로 셀 수 있는 신호만."""
from __future__ import annotations

from src.domain.services.ai_tell import find_ai_tells


def test_사람이_쓴_듯한_글은_지적이_없다():
    body = "## 설치\n\n설치는 금방 끝난다. 명령 한 줄이면 된다.\n\n막히면 로그부터 본다."
    assert find_ai_tells(body) == ()


def test_연결어미_쉼표가_6회_넘으면_지적한다():
    body = "설정을 바꾸고, 저장하며, 재시작하지만, 다시 열고, 확인하면서, 끝내고, 닫는다."
    assert any("연결어미" in t for t in find_ai_tells(body))


def test_결산_표현과_과장어를_센다():
    body = ("결론적으로 좋다. 따라서 쓴다. 요약하면 쉽다. 정리하자면 끝이다. "
            "혁신적이고 획기적이며 압도적이다.")
    tells = find_ai_tells(body)
    assert any("결산" in t for t in tells)
    assert any("과장" in t for t in tells)


def test_코드블록과_사진_표시는_세지_않는다():
    code = "```bash\n" + "echo a, b, c\n" * 3 + "# 따라서 결론적으로 요약하면 정리하자면\n```\n"
    body = code + "<!-- 사진: 결론적으로 따라서 -->\n본문은 짧다."
    assert find_ai_tells(body) == ()


def test_콜론_부제_소제목_반복을_지적한다():
    body = "## 개념: 정의\n\n가.\n\n## 구조: 원리\n\n나.\n\n## 비교: 차이\n\n다."
    assert any("소제목" in t for t in find_ai_tells(body))


def test_순서_소제목과_명사_고는_세지_않는다():
    steps = "".join(f"### {i}단계: 할 일\n\n본문.\n\n" for i in range(1, 6))
    nouns = "참고, 최고, 광고, 재고, 참고, 최고, 광고"
    assert find_ai_tells(steps + nouns) == ()
