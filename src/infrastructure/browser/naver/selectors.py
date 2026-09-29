"""네이버 SmartEditor ONE 셀렉터 Fallback Chain.

출처(MIT): choigpt-ai/naver-blog-automation `config/selectors.py`,
0x8905/naver-blog-automation `taste/default/selectors.json` (2026-09 기준)을 합쳤다.
해시가 붙은 클래스(save_btn__m9KHH 등)는 빌드마다 바뀌므로 부분 일치로 쓴다.
네이버가 DOM을 바꾸면 이 파일만 고친다.
"""
from __future__ import annotations

# /{blog_id}/postwrite 는 블로그 홈으로 튕기는 경우가 있었다. 이 경로는 매번
# #mainFrame 안에 PostWriteForm.naver 를 연다(2026-09-23 실측).
WRITE_PATH = "/{blog_id}?Redirect=Write&categoryNo=0"
# 발행 글 수정: #mainFrame 안에 PostUpdateForm.naver 가 기존 제목·본문을 불러온 채 열린다
# (2026-09-29 실측, MCP란·챗GPT 엑셀 글)
UPDATE_PATH = "/{blog_id}?Redirect=Update&logNo={log_no}"

# 편집 화면 구성 요소. 본문을 다 비우면 제목 + 빈 텍스트 = 2개가 남는다(2026-09-29 실측 19→2)
COMPONENTS = ".se-component"

MAIN_FRAME = "#mainFrame"

EDITOR_READY = [".se-section-documentTitle"]

# 제목·본문을 클릭하면 포커스가 이 숨은 iframe(id="input_buffer<숫자>")의 body로 간다.
# 키 입력과 paste 이벤트는 여기로 보내야 에디터가 받는다.
INPUT_BUFFER_FRAME = "iframe[id^='input_buffer']"

# "작성 중인 글이 있습니다" → 취소(새 글), 도움말 패널 닫기
POPUP_CLOSE = [
    "button.se-popup-button-cancel",
    "button.se-help-panel-close-button",
    "button.btn_close",
]

TITLE = [
    ".se-section-documentTitle",
    ".se-documentTitle .se-text-paragraph",
]

BODY = [
    ".se-section-text",
    ".se-component.se-text .se-text-paragraph",
]

# 붙여넣기 반영 확인용 — 편집 화면 문단(제목 포함). .se-main-container 는 보기 화면에만 있다.
# .se-component 개수는 쓰지 않는다: 표 없는 본문은 기존 텍스트 컴포넌트 하나에 들어가
# 개수가 그대로다(2026-09-23 실측 2→2, 본문은 정상 입력됨).
BODY_PARAGRAPHS = ".se-text-paragraph"

# 업로드가 끝난 사진. 붙여넣는 즉시 '전송중' 빈 사진 칸이 먼저 생기므로 칸 수로 판정하면
# 업로드 도중 다음 글을 붙여넣어 '파일 전송 오류'가 난다(2026-09-24 실측).
UPLOADED_IMAGES = ".se-component.se-image img[src*='pstatic.net']"

# '파일 전송 오류' 창 — 떠 있으면 이후 붙여넣기가 막힌다
UPLOAD_ERROR_CLOSE = [
    "button.se-popup-button-confirm",
    "//div[contains(@class, 'se-popup')]//button[contains(normalize-space(), '확인')]",
]

SAVE_DRAFT = [
    "button[class^='save_btn__']",
    "button[class*='save_btn']",
    "//button[contains(normalize-space(), '저장')]",
]

# 상단 '발행' → 설정 레이어가 열리고, 그 안의 '발행'이 최종 확인
PUBLISH_OPEN = [
    "button[class*='publish_btn']",
    "//button[normalize-space()='발행']",
]

# 발행 레이어의 카테고리 선택 상자(2026-09-24 실측: selectbox_button__해시, 목록도 selectbox 안)
CATEGORY_BUTTON = ["button[class*='selectbox_button']"]
# 항목은 <label for="7_TechNova">. 하위 카테고리는 숨은 '하위 카테고리' 글자가 붙어
# 글자 비교로는 안 잡힌다
CATEGORY_OPTION = "label[for$='_{name}']"

# 발행 레이어에 이미 붙은 태그(수정 화면이 불러온 것).
# 태그 입력란에서 백스페이스 1번에 1개씩 지워진다(2026-09-29 실측)
EXISTING_TAGS = "span[id^='tag-item-']"

TAG_INPUT = [
    "input[placeholder*='태그']",
    "input[class*='tag_input']",
]

PUBLISH_CONFIRM = [
    "button[class*='confirm_btn']",
    "//div[contains(@class, 'layer')]//button[contains(normalize-space(), '발행')]",
]

# --- 로그인 페이지 (nid.naver.com) — 자동 로그인(login.py) 전용 ---
LOGIN_ID_INPUT = "input#id"
LOGIN_PW_INPUT = "input#pw"
LOGIN_SUBMIT = "#log\\.login"
LOGIN_CAPTCHA = "#captcha"
# '로그인 상태 유지' — 없으면 경고만 하고 진행한다
LOGIN_KEEP = ["input#keep", "input[name='nvlong']"]
# 판정 문구. 네이버가 문구를 바꾸면 결과 불명으로 끝난다(성공으로 넘어가지 않음)
LOGIN_BLOCKED_MARKERS = ["자동입력 방지", "보호조치"]
LOGIN_WRONG_PASSWORD_MARKERS = ["비밀번호를 잘못"]
LOGIN_APPROVAL_MARKERS = ["2단계 인증", "인증 요청", "알림을 보냈"]
# 승인 뒤 '새로운 기기 등록' 화면 — 등록을 눌러야 다음 로그인에서 다시 묻지 않는다
LOGIN_DEVICE_MARKERS = ["새로운 기기", "자주 사용하는 기기"]
LOGIN_DEVICE_REGISTER = "//button[normalize-space()='등록'] | //a[normalize-space()='등록']"
