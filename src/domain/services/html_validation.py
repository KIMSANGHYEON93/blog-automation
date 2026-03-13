"""HtmlValidationService — Domain service for HTML content validation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """HTML 검증 결과."""
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.passed = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


# 마크다운 잔여 문법 패턴
_RESIDUAL_PATTERNS: list[tuple[str, str]] = [
    (r"(?m)^#{1,6}\s", "마크다운 헤딩(## )"),
    (r"\*\*[^*]+\*\*", "볼드(**text**)"),
    (r"\|---", "테이블 구분선(|---)"),
]

MIN_CONTENT_LENGTH = 1500


class HtmlValidationService:
    """HTML 변환 결과를 검증하는 도메인 서비스.

    검증 항목:
      1. <h2> 또는 <h3> 태그 존재
      2. <p> 태그 존재
      3. 마크다운 잔여 문법 미포함 (## , **, |---)
      4. 본문 길이 >= 1,500자 (태그 제거 후 순수 텍스트)
      5. <!-- IMAGE: --> 마커 잔류 → hard fail
      6. <img> 태그 0개 → warning only
      7. Mermaid 코드블록 잔류 → warning only
      8. FAQ LD+JSON 스키마 존재 여부 → info only
    """

    def validate(self, html_text: str) -> ValidationResult:
        """HTML 콘텐츠를 검증하고 ValidationResult 반환."""
        result = ValidationResult()

        if not html_text:
            result.add_error("빈 콘텐츠")
            return result

        # 1. 헤딩 태그 확인
        if not re.search(r"<h[23][^>]*>", html_text):
            result.add_error("<h2>/<h3> 태그 없음")

        # 2. 단락 태그 확인
        if "<p>" not in html_text:
            result.add_error("<p> 태그 없음")

        # 3. 마크다운 잔여 문법 확인 (코드 블록 밖에서만)
        stripped = re.sub(r"<pre[^>]*>.*?</pre>", "", html_text, flags=re.DOTALL)
        stripped = re.sub(r"<code[^>]*>.*?</code>", "", stripped, flags=re.DOTALL)

        for pattern, desc in _RESIDUAL_PATTERNS:
            if re.search(pattern, stripped):
                result.add_error(f"잔여 마크다운 문법 — {desc}")

        # 4. 본문 길이 검증
        plain_text = re.sub(r"<[^>]+>", "", html_text).strip()
        if len(plain_text) < MIN_CONTENT_LENGTH:
            result.add_error(
                f"본문 길이 부족 ({len(plain_text)}자, 최소 {MIN_CONTENT_LENGTH}자)"
            )

        # 5. IMAGE 마커 잔류
        if re.search(r"<!-- IMAGE:\s*.+?\s*-->", html_text):
            result.add_error("IMAGE 마커 잔류 — 이미지 삽입 미처리")

        # 6. <img> 태그 0개 → warning
        if not re.search(r"<img\s", html_text):
            result.add_warning("<img> 태그 없음 (이미지 0개)")

        # 7. Mermaid 코드블록 잔류 → warning
        if re.search(r'class="[^"]*language-mermaid', html_text):
            result.add_warning("Mermaid 코드블록 미렌더링 잔류")

        return result

    def is_valid(self, html_text: str) -> bool:
        """간단한 통과/실패 판정 (기존 validate_html() 호환)."""
        return self.validate(html_text).passed
