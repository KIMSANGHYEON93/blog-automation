"""AI 티 점검 — 생성된 한국어 본문에서 사람 글과 갈리는 문체 신호를 센다.

기준은 humanize-korean 룰북(quick-rules)의 패턴 중 정규식으로 셀 수 있는 것만 옮겼다.
발행을 막지 않고 대시보드에 보여 주기만 한다 — 문턱값이 사람 글에도 걸릴 수 있어서다.
생성 프롬프트(n8n route_prompt_workflow.js styleNote, prompt_naver_common.md)에도
같은 규칙이 들어가 있으니 규칙을 바꾸면 세 곳을 함께 고칠 것.
"""
from __future__ import annotations

import re

_CODE = re.compile(r"```.*?```|\[MERMAID\].*?\[/MERMAID\]|<!--.*?-->", re.S)

# (설명, 패턴, 지적 문턱 — 이 횟수 이상이면 지적)
_RULES: tuple[tuple[str, re.Pattern[str], int], ...] = (
    ("연결어미 뒤 쉼표(~하고, ~하며,)",
     re.compile(r"(?<![참최광재])(?:고|며|지만|면서|아서|어서|으며),"), 6),
    ("결산 표현(결론적으로·따라서·요약하면 등)",
     re.compile(r"결론적으로|따라서|이를 통해|그러므로|요약하면|정리하자면"), 4),
    ("과장어(혁신적·획기적·압도적·완벽한 등)",
     re.compile(r"혁신적|획기적|압도적|파격적|폭발적|전례 없는|완벽한|완벽하게"), 3),
    ("의의 과장(매우 중요하다·주목할 만하다 등)",
     re.compile(r"매우 중요|주목할 만|시사하는 바가 크"), 2),
    ("분열문(중요한 것은·핵심은 ~이다)", re.compile(r"(?:중요한|필요한) 것은|핵심은|관건은"), 3),
    ("'단순한 X를 넘어' 공식", re.compile(r"단순(?:한|히) [^.\n]{1,30}?넘어"), 1),
    ("'~할 때입니다' 결말 공식", re.compile(r"(?:할|볼) 때입니다|시점입니다"), 2),
    ("이중 피동(되어진다)", re.compile(r"되어지|되어져"), 1),
    ("'~에 있어서' 번역투", re.compile(r"에 있어서?"), 3),
    ("목록 도입구(다음과 같습니다 등)",
     re.compile(r"다음과 같(?:습니다|다)|크게 [두세네] 가지"), 3),
)
# "1단계: X" 같은 순서 소제목은 정상이라 숫자로 시작하면 세지 않는다
_COLON_HEADING = re.compile(r"^#{2,3} (?!\d)[^\n:]+: ", re.M)
_COLON_HEADING_LIMIT = 3


def find_ai_tells(markdown: str) -> tuple[str, ...]:
    """문턱을 넘은 AI 티 목록. 코드·다이어그램·HTML 주석은 세지 않는다."""
    text = _CODE.sub("", markdown or "")
    found = []
    for label, pattern, limit in _RULES:
        count = len(pattern.findall(text))
        if count >= limit:
            found.append(f"{label} {count}회")
    headings = len(_COLON_HEADING.findall(text))
    if headings >= _COLON_HEADING_LIMIT:
        found.append(f"콜론 부제 소제목(X: Y) {headings}개")
    return tuple(found)
