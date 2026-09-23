"""한국어 조사 선택 — 받침 유무로 '이란'/'란'을 고른다.

'LLM란', 'HHH 원칙란'처럼 틀린 조사는 검색어로도 어색하고 제목 품질을 떨어뜨린다.
영문 약어는 철자가 아니라 한국어 읽기의 끝소리로 판정한다(LLM=엘엘엠 → 받침 ㅁ).
"""
from __future__ import annotations

_HANGUL_START = 0xAC00
_HANGUL_END = 0xD7A3
_JONGSEONG_COUNT = 28

# 알파벳 한 글자를 한국어로 읽었을 때 받침이 남는지.
# 예: L=엘(ㄹ), M=엠(ㅁ), N=엔(ㄴ), K=케이(없음)
_LATIN_HAS_FINAL = {
    "l": True, "m": True, "n": True, "r": True,
}

# 숫자 한 글자를 한국어로 읽었을 때. 삼(ㅁ), 육(ㄱ), 칠(ㄹ), 영(ㅇ), 일(ㄹ)...
# 1은 '원'으로도 읽히지만 '일'이 기본이라 받침 있음으로 볼 수도 있다.
# 실무에선 "1이란"보다 "1이란"… 혼란을 줄이려 숫자는 관용 표기를 따른다.
_DIGIT_HAS_FINAL = {
    "0": True,   # 영 → ㅇ
    "1": False,  # 원 (버전·항목 표기에서 흔한 읽기)
    "2": False,  # 이
    "3": True,   # 삼 → ㅁ
    "4": False,  # 사
    "5": False,  # 오
    "6": True,   # 육 → ㄱ
    "7": True,   # 칠 → ㄹ
    "8": False,  # 팔 → ㄹ 이지만 관용상 '8이란'이 어색해 제외
    "9": False,  # 구
}


def _last_meaningful_char(text: str) -> str:
    """받침 판정에 쓸 마지막 글자. 괄호·기호는 건너뛴다."""
    for ch in reversed(text):
        if ch.isalnum():
            return ch
    return ""


def has_final_consonant(text: str) -> bool:
    """마지막 글자에 받침이 있는가."""
    ch = _last_meaningful_char(text)
    if not ch:
        return False
    code = ord(ch)
    if _HANGUL_START <= code <= _HANGUL_END:
        return (code - _HANGUL_START) % _JONGSEONG_COUNT != 0
    if ch.isdigit():
        return _DIGIT_HAS_FINAL.get(ch, False)
    return _LATIN_HAS_FINAL.get(ch.lower(), False)


def with_iran(name: str) -> str:
    """'<용어>란' / '<용어>이란' 중 맞는 쪽을 붙인다."""
    if not name:
        return ""
    return f"{name}이란" if has_final_consonant(name) else f"{name}란"
