"""네이버 SmartEditor ONE 셀렉터 Fallback Chain.

출처(MIT): choigpt-ai/naver-blog-automation `config/selectors.py`,
0x8905/naver-blog-automation `taste/default/selectors.json` (2026-09 기준)을 합쳤다.
해시가 붙은 클래스(save_btn__m9KHH 등)는 빌드마다 바뀌므로 부분 일치로 쓴다.
네이버가 DOM을 바꾸면 이 파일만 고친다.
"""
from __future__ import annotations

WRITE_PATH = "/{blog_id}/postwrite"

# 구버전 글쓰기 화면은 #mainFrame iframe 안에 에디터가 있다. 없으면 최상위 문서.
MAIN_FRAME = "#mainFrame"

EDITOR_READY = [".se-content", ".se-editor", ".se-section-documentTitle"]

# "작성 중인 글이 있습니다" → 취소(새 글), 도움말 패널 닫기
POPUP_CLOSE = [
    "button.se-popup-button-cancel",
    "button.se-help-panel-close-button",
    "button.btn_close",
]

TITLE = [
    ".se-section-documentTitle .se-module-text",
    ".se-documentTitle .se-text-paragraph",
    ".se-section-documentTitle",
]

BODY = [
    ".se-section-text .se-module-text",
    ".se-component.se-text .se-text-paragraph",
    "div.se-section-text div[contenteditable='true']",
]

# 본문 붙여넣기가 먹혔는지 셀 때 쓰는 컴포넌트
BODY_COMPONENTS = ".se-main-container .se-component"

SAVE_DRAFT = [
    "button[class*='save_btn']",
    "//button[contains(normalize-space(), '저장')]",
]

# 상단 '발행' → 설정 레이어가 열리고, 그 안의 '발행'이 최종 확인
PUBLISH_OPEN = [
    "button[class*='publish_btn']",
    "//button[normalize-space()='발행']",
]

TAG_INPUT = [
    "input[placeholder*='태그']",
    "input[class*='tag_input']",
]

PUBLISH_CONFIRM = [
    "button[class*='confirm_btn']",
    "//div[contains(@class, 'layer')]//button[contains(normalize-space(), '발행')]",
]
