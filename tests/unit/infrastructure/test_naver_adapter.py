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
    monkeypatch.setattr(editor, "paste_body", lambda sb, h, p: log.append(("body", h)))
    monkeypatch.setattr(editor, "save_draft", lambda sb: log.append(("draft",)))

    def fake_publish(sb, tags):
        log.append(("publish", tags))
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

    monkeypatch.setattr(editor, "paste_body", broken)
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

    monkeypatch.setattr(editor, "paste_body", broken)
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

    monkeypatch.setattr(editor, "paste_body", broken)
    adapter = NaverBrowserAdapter("myblog", draft_only=False, screenshot_dir=str(tmp_path))
    assert not adapter.publish(_post()).success  # _sb None — 예외 없이 실패 결과


def test_발행_URL_미확인은_수동_확인_필요로_표시(calls, monkeypatch):
    def unconfirmed(sb, tags):
        raise editor.NaverEditorError(
            f"발행 후 글 URL을 확인하지 못함 — {editor.PUBLISH_UNCONFIRMED}"
        )

    monkeypatch.setattr(editor, "publish", unconfirmed)
    result = NaverBrowserAdapter("myblog", draft_only=False).publish(_post())
    assert not result.success
    assert editor.PUBLISH_UNCONFIRMED in result.error


def test_발행_확인_뒤_일반_예외도_수동_확인_필요로_바꾼다(monkeypatch):
    # 확인 버튼을 누른 뒤에는 실제로 발행됐을 수 있다 — 재발행하지 않게 표식을 남겨야 한다
    monkeypatch.setattr(editor, "_click_first", lambda sb, s, name: None)
    monkeypatch.setattr(editor.time, "sleep", lambda s: None)

    def driver_died(sb):
        raise RuntimeError("chrome not reachable")

    monkeypatch.setattr(editor, "_wait_published_url", driver_died)
    with pytest.raises(editor.NaverEditorError, match=editor.PUBLISH_UNCONFIRMED):
        editor.publish(object(), [])
