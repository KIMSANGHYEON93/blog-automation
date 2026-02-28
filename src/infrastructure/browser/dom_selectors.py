from __future__ import annotations

"""
DOM 셀렉터 Fallback Chain
티스토리 에디터 DOM 변경에 대응하기 위해 우선순위 순으로 정의
(2026-02-28 실제 DOM 기준)
"""

# 에디터 URL (manage/post/write는 deprecated → manage/newpost 사용)
EDITOR_PATH = "/manage/newpost"

TITLE_SELECTORS = [
    "#post-title-inp",
    "textarea.textarea_tit",
]

# 에디터 모드 전환 (기본모드 → 마크다운 전환)
MODE_SWITCH_BUTTON_SELECTORS = [
    "#editor-mode-layer-btn-open",
]

MARKDOWN_MODE_SELECTORS = [
    "#editor-mode-markdown",
]

# 마크다운 모드 전환 후 CodeMirror 에디터
CONTENT_AREA_SELECTORS = [
    ".CodeMirror",
    "textarea.mce-textbox",
    "#content-area",
]

# TinyMCE iframe (기본모드에서 사용)
TINYMCE_IFRAME_SELECTORS = [
    "#editor-tistory_ifr",
]

SAVE_BUTTON_SELECTORS = [
    "a.action",            # 임시저장 링크
]

PUBLISH_BUTTON_SELECTORS = [
    "#publish-layer-btn",  # 완료 버튼
]

TAG_INPUT_SELECTORS = [
    "#tagText",
]


def find_element(sb, selectors: list[str], timeout: int = 10) -> str | None:
    """Fallback Chain으로 첫 번째 존재하는 셀렉터 반환."""
    per_selector_timeout = max(1, timeout // len(selectors))
    for selector in selectors:
        try:
            sb.wait_for_element_present(selector, timeout=per_selector_timeout)
            return selector
        except Exception:
            continue
    return None
