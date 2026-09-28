"""NaverBrowserAdapter 흐름 테스트 — editor 모듈을 가짜로 바꿔 브라우저 없이 검증."""
import pytest

from src.domain.entities.post import Post
from src.domain.value_objects.post_content import PostContent
from src.infrastructure.browser.naver import adapter as adapter_mod
from src.infrastructure.browser.naver import editor
from src.infrastructure.browser.naver.adapter import DRAFT_ONLY_MESSAGE, NaverBrowserAdapter

PUBLISHED = "https://blog.naver.com/myblog/223456789012"


@pytest.fixture
def calls(monkeypatch):
    log: list[tuple] = []
    monkeypatch.setattr(editor, "open_editor", lambda sb, blog: log.append(("open", blog)))
    monkeypatch.setattr(editor, "fill_title", lambda sb, t: log.append(("title", t)))
    monkeypatch.setattr(editor, "focus_body", lambda sb: log.append(("focus",)))
    monkeypatch.setattr(editor, "paste_html", lambda sb, h, p: log.append(("body", h)))
    monkeypatch.setattr(editor, "paste_image", lambda sb, data: log.append(("image", data)) or True)
    monkeypatch.setattr(editor, "save_draft", lambda sb: log.append(("draft",)))

    def fake_publish(sb, tags, category=""):
        log.append(("publish", tags))
        log.append(("category", category))
        return PUBLISHED

    monkeypatch.setattr(editor, "publish", fake_publish)
    monkeypatch.setattr(adapter_mod.time, "sleep", lambda s: None)
    return log


def _post(body: str = "## 소제목\n\n본문", tags: str = "API, #쿠버네티스") -> Post:
    content = PostContent(title="제목", body_markdown=body, tags=tags)
    return Post(row_index=2, keyword="키워드", content=content)


def test_draft_only_saves_and_reports_not_published(calls):
    result = NaverBrowserAdapter("myblog").publish(_post())
    assert not result.success
    assert result.error == DRAFT_ONLY_MESSAGE
    assert ("draft",) in calls
    assert not any(c[0] == "publish" for c in calls)


def test_public_publish_returns_url_and_log_no(calls):
    result = NaverBrowserAdapter("myblog", draft_only=False).publish(_post())
    assert result.success
    assert result.url == PUBLISHED
    assert result.entry_id == "223456789012"
    assert ("title", "제목") in calls
    assert ("publish", ["API", "쿠버네티스"]) in calls


def test_editor_error_becomes_failed_result(calls, monkeypatch):
    def broken(sb, html, plain):
        raise editor.NaverEditorError("본문 붙여넣기가 반영되지 않음")

    monkeypatch.setattr(editor, "paste_html", broken)
    result = NaverBrowserAdapter("myblog", draft_only=False).publish(_post())
    assert not result.success
    assert "붙여넣기" in result.error


def test_empty_body_is_rejected_before_opening_editor(calls):
    result = NaverBrowserAdapter("myblog").publish(_post(body=""))
    assert not result.success
    assert calls == []


def test_write_url_uses_redirect_write_entry():
    # /postwrite 는 블로그 홈으로 튕기는 경우가 있었다(2026-09-23 실측)
    assert editor.write_url("myblog") == (
        "https://blog.naver.com/myblog?Redirect=Write&categoryNo=0"
    )


def test_update_is_not_supported(calls):
    assert not NaverBrowserAdapter("myblog").update(_post()).success


class _FakeSb:
    def __init__(self):
        self.screenshots: list[str] = []

    def save_screenshot(self, path: str) -> None:
        self.screenshots.append(path)


def test_실패하면_스크린샷을_남긴다(calls, monkeypatch, tmp_path):
    def broken(sb, html, plain):
        raise editor.NaverEditorError("본문 붙여넣기가 반영되지 않음")

    monkeypatch.setattr(editor, "paste_html", broken)
    adapter = NaverBrowserAdapter("myblog", draft_only=False, screenshot_dir=str(tmp_path))
    fake = _FakeSb()
    adapter._sb = fake
    adapter.publish(_post())
    assert len(fake.screenshots) == 1
    assert fake.screenshots[0].startswith(str(tmp_path))
    assert "row2" in fake.screenshots[0]


def test_브라우저가_없어도_스크린샷_단계에서_죽지_않는다(calls, monkeypatch, tmp_path):
    def broken(sb, html, plain):
        raise editor.NaverEditorError("실패")

    monkeypatch.setattr(editor, "paste_html", broken)
    adapter = NaverBrowserAdapter("myblog", draft_only=False, screenshot_dir=str(tmp_path))
    assert not adapter.publish(_post()).success  # _sb None — 예외 없이 실패 결과


def test_발행_URL_미확인은_수동_확인_필요로_표시(calls, monkeypatch):
    def unconfirmed(sb, tags, category=""):
        raise editor.NaverEditorError(
            f"발행 후 글 URL을 확인하지 못함 — {editor.PUBLISH_UNCONFIRMED}"
        )

    monkeypatch.setattr(editor, "publish", unconfirmed)
    result = NaverBrowserAdapter("myblog", draft_only=False).publish(_post())
    assert not result.success
    assert editor.PUBLISH_UNCONFIRMED in result.error


class _EditorSb:
    """본문 붙여넣기 판정용 가짜 — 붙여넣으면 셀렉터별 개수가 바뀐다."""

    def __init__(self, before: dict, after: dict):
        self.counts, self._after = before, after

    def is_element_visible(self, selector):
        return True

    def click(self, selector):
        pass

    def execute_script(self, script, selector):
        return self.counts.get(selector, 0)

    def paste(self):
        self.counts = self._after


def _paste_with(monkeypatch, sb):
    monkeypatch.setattr(editor.time, "sleep", lambda s: None)
    monkeypatch.setattr(editor, "_dispatch_paste_in_input_buffer", lambda s, h, p: sb.paste())
    editor.paste_body(sb, "<p>본문</p>", "본문")


def test_표_없는_본문은_컴포넌트가_늘지_않아도_글자가_늘면_성공(monkeypatch):
    # 2026-09-23 실측: 텍스트만 있는 본문은 기존 텍스트 컴포넌트 하나에 들어가 .se-component 2→2
    # 2026-09-24 실측: 빈 문단에 한 줄을 붙이면 문단 수도 2→2 — 글자 수로 판정한다
    sb = _EditorSb(
        before={".se-component": 2, ".se-text-paragraph": 0},
        after={".se-component": 2, ".se-text-paragraph": 12},
    )
    _paste_with(monkeypatch, sb)  # 예외 없음


def test_글자가_그대로면_붙여넣기_실패(monkeypatch):
    sb = _EditorSb(
        before={".se-component": 2, ".se-text-paragraph": 2},
        after={".se-component": 2, ".se-text-paragraph": 2},
    )
    with pytest.raises(editor.NaverEditorError, match="붙여넣기"):
        _paste_with(monkeypatch, sb)


def test_발행_확인_뒤_일반_예외도_수동_확인_필요로_바꾼다(monkeypatch):
    # 확인 버튼을 누른 뒤에는 실제로 발행됐을 수 있다 — 재발행하지 않게 표식을 남겨야 한다
    monkeypatch.setattr(editor, "_click_first", lambda sb, s, name: None)
    monkeypatch.setattr(editor.time, "sleep", lambda s: None)

    def driver_died(sb):
        raise RuntimeError("chrome not reachable")

    monkeypatch.setattr(editor, "_wait_published_url", driver_died)
    with pytest.raises(editor.NaverEditorError, match=editor.PUBLISH_UNCONFIRMED):
        editor.publish(object(), [])


def _sectioned_post(n_headings: int) -> Post:
    body = "도입 문장.\n\n" + "\n\n".join(f"## 소제목{i}\n\n본문{i}." for i in range(n_headings))
    return _post(body=body)


def test_사진은_도입부_대표와_소제목마다_최대_5장(calls):
    prompts: list[str] = []

    def image_fn(prompt):
        prompts.append(prompt)
        return b"jpg"

    adapter = NaverBrowserAdapter("myblog", draft_only=False, image_fn=image_fn)
    assert adapter.publish(_sectioned_post(6)).success
    kinds = [c[0] for c in calls if c[0] in ("image", "body")]
    assert kinds[:3] == ["image", "body", "body"]  # 대표 사진 → 도입부 → 첫 소제목
    assert kinds.count("image") == 5
    assert "키워드" in prompts[0]
    assert "소제목0" in prompts[1]


def test_사진은_소제목_바로_아래(calls):
    adapter = NaverBrowserAdapter("myblog", draft_only=False, image_fn=lambda p: b"jpg")
    adapter.publish(_sectioned_post(1))
    order = [c for c in calls if c[0] in ("image", "body")]
    assert "소제목0" in order[2][1] and order[3][0] == "image" and "본문0" in order[4][1]


def test_사진_생성이_실패해도_발행한다(calls):
    adapter = NaverBrowserAdapter("myblog", draft_only=False, image_fn=lambda p: None)
    assert adapter.publish(_sectioned_post(2)).success
    assert not any(c[0] == "image" for c in calls)


def test_사진_함수가_없으면_사진_없이(calls):
    assert NaverBrowserAdapter("myblog", draft_only=False).publish(_sectioned_post(2)).success
    assert not any(c[0] == "image" for c in calls)


class _LayerSb:
    """발행 레이어 가짜 — 보이는 셀렉터와 클릭·입력 기록."""

    def __init__(self, visible):
        self.visible, self.log = set(visible), []

    def is_element_visible(self, selector):
        return selector in self.visible

    def click(self, selector):
        self.log.append(("click", selector))

    def add_text(self, selector, text):
        self.log.append(("add_text", text))

    def type(self, selector, text):
        self.log.append(("type", text))


def test_태그는_지우지_않고_이어_쓴다(monkeypatch):
    # sb.type은 입력란을 지운 뒤 쓴다 — 마지막 태그만 남았다(2026-09-23 실측)
    monkeypatch.setattr(editor.time, "sleep", lambda s: None)
    sb = _LayerSb({editor.sel.TAG_INPUT[0]})
    editor._fill_tags(sb, ["가", "나", "다"])
    assert [e for e in sb.log if e[0] == "add_text"] == [
        ("add_text", "가\n"), ("add_text", "나\n"), ("add_text", "다\n"),
    ]
    assert not any(e[0] == "type" for e in sb.log)


def test_카테고리는_목록에서_이름이_같은_항목을_고른다(monkeypatch):
    monkeypatch.setattr(editor.time, "sleep", lambda s: None)
    option = editor.sel.CATEGORY_OPTION.format(name="TechNova")
    sb = _LayerSb({editor.sel.CATEGORY_BUTTON[0], option})
    assert editor._select_category(sb, "TechNova") is True
    assert sb.log == [("click", editor.sel.CATEGORY_BUTTON[0]), ("click", option)]


def test_없는_카테고리면_기본값으로_두고_목록을_닫는다(monkeypatch):
    monkeypatch.setattr(editor.time, "sleep", lambda s: None)
    sb = _LayerSb({editor.sel.CATEGORY_BUTTON[0]})
    assert editor._select_category(sb, "없는카테고리") is False
    assert sb.log == [("click", editor.sel.CATEGORY_BUTTON[0])] * 2


def test_발행에_시트_카테고리를_넘긴다(calls):
    post = _post()
    post.category = "TechNova"
    NaverBrowserAdapter("myblog", draft_only=False).publish(post)
    assert ("category", "TechNova") in calls


def test_발행_뒤_공개_글을_점검해_경고를_돌려준다(calls, monkeypatch):
    stats = {"category": "낙서장", "tags": 2, "images": 1, "quotes": 1, "orphan_numbers": 0}
    monkeypatch.setattr(editor, "collect_post_stats", lambda sb, url: stats)
    post = _post()
    post.category = "TechNova"
    result = NaverBrowserAdapter("myblog", draft_only=False).publish(post)
    assert result.success
    assert "카테고리가 '낙서장'(기대 'TechNova')" in result.warnings


def test_점검이_실패해도_발행은_성공으로(calls, monkeypatch):
    def broken(sb, url):
        raise RuntimeError("page timeout")

    monkeypatch.setattr(editor, "collect_post_stats", broken)
    result = NaverBrowserAdapter("myblog", draft_only=False).publish(_post())
    assert result.success
    assert result.warnings == ("발행 후 점검을 하지 못함: page timeout",)


def test_첫_사진만_제목_썸네일로_바꾼다(calls):
    seen: list[tuple[str, bytes, str]] = []

    def thumbnail(title, data, keyword):
        seen.append((title, data, keyword))
        return b"thumb"

    adapter = NaverBrowserAdapter(
        "myblog", draft_only=False, image_fn=lambda p: b"jpg", thumbnail_fn=thumbnail,
    )
    adapter.publish(_sectioned_post(2))
    images = [c[1] for c in calls if c[0] == "image"]
    assert images == [b"thumb", b"jpg", b"jpg"]
    assert seen == [("제목", b"jpg", "키워드")]


def test_업로드_확인이_늦어도_붙인_사진은_한_장으로_센다(calls, monkeypatch):
    # 2026-09-26 실측: 45초 안에 확인 못 한 사진이 늦게 올라가 6장이 됐다
    def unconfirmed(sb, data):
        calls.append(("image", data))
        return False

    monkeypatch.setattr(editor, "paste_image", unconfirmed)
    adapter = NaverBrowserAdapter("myblog", draft_only=False, image_fn=lambda p: b"jpg")
    adapter.publish(_sectioned_post(6))
    assert sum(1 for c in calls if c[0] == "image") == 5
