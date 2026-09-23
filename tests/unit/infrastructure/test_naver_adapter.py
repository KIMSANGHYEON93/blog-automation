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


def test_update_is_not_supported(calls):
    assert not NaverBrowserAdapter("myblog").update(_post()).success
