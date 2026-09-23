"""BrainTerm — AI-Brain 볼트의 용어 카드 (Domain Value Object).

GSC 기반 발굴은 '이미 노출된 쿼리'만 돌려주므로 트래픽 없는 주제가 영원히
빠진다(트래픽 없음 → 키워드 없음 → 글 없음 → 트래픽 없음). 볼트 용어는
트래픽과 무관한 시드라 이 루프를 끊는다.

scripts/sync_brain_terms.py에도 같은 이름의 dataclass가 있으나 그쪽은
Drive 마크다운 → 시트 행 변환용 DTO다. 이 파일은 키워드 생성 '규칙'을 담는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.domain.services.korean_particle import with_iran

# 혼동포인트 형식: "A ≠ B. 설명..." — 볼트 381건 중 376건(98%)이 이 형태다.
_CONFUSION_RE = re.compile(r"^\s*.+?\s*(?:≠|!=)\s*(.+?)\s*(?:[.。]|$)")

# 마크다운 링크 [표시텍스트](파일.md) → 표시텍스트
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")

# 괄호 병기 제거: "비판적 감식(Discernment)" → "비판적 감식"
_PAREN_RE = re.compile(r"\s*[(（][^)）]*[)）]\s*$")

# 검색어가 못 되는 서술형 대상. "단순 프롬프트 엔지니어링 기법" 같은 값이
# 혼동포인트에 흔한데, 그대로 키워드로 쓰면 검색량이 0이다.
_DESCRIPTIVE_PREFIXES = ("단순", "일반", "기존", "무조건", "평범")

_MAX_TARGET_LEN = 20
_MIN_TARGET_LEN = 2


def _clean_target(raw: str) -> str:
    """혼동 대상 문자열을 검색어에 가깝게 정리."""
    value = _PAREN_RE.sub("", raw.strip()).strip()
    return value.strip("`\'\"·-— ")


@dataclass(frozen=True)
class BrainTerm:
    """용어 카드 한 장.

    aliases_raw / confusion_raw는 시트 원본 문자열을 그대로 받는다 —
    파싱 규칙을 Domain 안에 두어 어댑터가 바뀌어도 규칙이 흔들리지 않는다.
    """

    name: str
    definition: str
    aliases_raw: str = ""
    confusion_raw: str = ""
    source: str = ""
    aliases: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError("용어 이름이 비어 있습니다")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "definition", self.definition.strip())
        object.__setattr__(self, "aliases", self._split_aliases())

    def _split_aliases(self) -> tuple[str, ...]:
        parts = (p.strip() for p in self.aliases_raw.split(","))
        return tuple(p for p in parts if len(p) > 1)

    def confusion_target(self) -> str | None:
        """비교 글로 쓸 만한 혼동 대상. 없으면 None.

        서술형("단순 ~")·과도하게 긴 값·자기 자신은 검색어가 못 되므로 버린다.
        """
        # 링크를 먼저 없앤다 — [용어](파일.md)의 .md가 문장 끝으로 오인된다.
        raw = _MD_LINK_RE.sub(r"\1", self.confusion_raw)
        match = _CONFUSION_RE.match(raw)
        if not match:
            return None
        target = _clean_target(match.group(1))
        if not (_MIN_TARGET_LEN <= len(target) <= _MAX_TARGET_LEN):
            return None
        if target.startswith(_DESCRIPTIVE_PREFIXES):
            return None
        # "토큰 ≠ 단어 ≠ 글자"처럼 부등호가 이어지면 대상이 하나로 안 잡히고,
        # "툴 유즈 / 함수 호출"처럼 슬래시로 묶인 병렬 개념도 검색어가 못 된다.
        if any(c in target for c in ("≠", "!=", "/")):
            return None
        if target.casefold() == self.name.casefold():
            return None
        return target

    def keyword_candidates(self) -> tuple[str, ...]:
        """이 용어에서 만들 수 있는 키워드.

        정의형이 비교형보다 검색 의도가 넓어 항상 먼저 온다.
        """
        candidates = [with_iran(self.name)]
        target = self.confusion_target()
        if target:
            candidates.append(f"{self.name} vs {target} 차이")
        return tuple(candidates)

    def priority(self) -> float:
        """검색 수요 대용 지표. 높을수록 먼저 쓴다.

        볼트에는 검색량이 없으므로 대리 지표를 쓴다 — 널리 쓰이는 용어일수록
        이름이 짧고(약어), 별칭이 여러 개 정리돼 있고, 출처가 달려 있다.
        """
        score = 0.0
        score += max(0.0, 20.0 - len(self.name))   # 짧을수록 유리
        score += min(len(self.aliases), 3) * 2.0    # 별칭 3개까지 가산
        if self.source.strip():
            score += 3.0
        return score

    def all_names(self) -> tuple[str, ...]:
        """용어 + 별칭. 기존 글과의 중복 판정에 쓴다."""
        return (self.name, *self.aliases)
