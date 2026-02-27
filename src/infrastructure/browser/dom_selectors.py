"""
DOM 셀렉터 Fallback Chain
티스토리 에디터 DOM 변경에 대응하기 위해 우선순위 순으로 정의
"""
from typing import List, Optional


MARKDOWN_MODE_SELECTORS = [
    "button.toolbar-markdown",
    "button[title='마크다운']",
    "#modeSwitch",
]

CONTENT_AREA_SELECTORS = [
    ".CodeMirror",
    "#content-area",
    "textarea[name='content']",
]

TITLE_SELECTORS = [
    "#post-title-inp",
    "input[name='title']",
]

SAVE_BUTTON_SELECTORS = [
    "button.btn-save",
    "button[onclick*='save']",
    "#save-btn",
]

PUBLISH_BUTTON_SELECTORS = [
    "button.btn-publish",
    "#btn-publish",
    "button[onclick*='publish']",
]


def find_element(sb, selectors: List[str], timeout: int = 10) -> Optional[str]:
    """Fallback Chain으로 첫 번째 존재하는 셀렉터 반환."""
    for selector in selectors:
        try:
            sb.wait_for_element_present(selector, timeout=timeout // len(selectors))
            return selector
        except Exception:
            continue
    return None
