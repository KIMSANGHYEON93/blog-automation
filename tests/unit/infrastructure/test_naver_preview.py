"""네이버 발행 미리보기 — 붙여넣을 HTML을 안전하게, 사진 자리와 함께."""
from src.infrastructure.browser.naver.preview import build_preview_html


def test_가운데_정렬은_클래스로_바꾼다():
    # 대시보드 CSP가 인라인 style을 막는다 — style 속성은 남기지 않는다
    html = build_preview_html("키워드", "첫 문장이에요. 둘째예요.")
    assert '<p class="c">첫 문장이에요.</p>' in html
    assert "style=" not in html


def test_사진_자리를_발행과_같은_순서로_표시():
    html = build_preview_html("감마", "도입.\n\n## 첫째\n\n가.")
    assert html.index("photo") < html.index("도입.")
    assert html.index("첫째</p></blockquote>") < html.rindex("photo") < html.index("가.")
    assert html.count('class="photo"') == 2


def test_스크립트와_이벤트_속성은_없앤다():
    html = build_preview_html(
        "k",
        '본문 <script>alert(1)</script> <img src=x onerror=alert(1)> [링크](javascript:alert(1))',
    )
    assert "<script" not in html and "onerror" not in html and "javascript:" not in html


def test_표와_목록은_남긴다():
    html = build_preview_html("k", "| a | b |\n|---|---|\n| 1 | 2 |\n\n- 가\n- 나")
    assert "<table" in html and "<li>가</li>" in html
