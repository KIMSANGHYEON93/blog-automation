"""티스토리 발행 — API 발행이 끝난 뒤 검증 단계 예외를 실패로 돌리지 않는다(재발행 중복 방지)."""
from __future__ import annotations

from types import SimpleNamespace

from src.domain.entities.post import Post
from src.domain.value_objects.post_content import PostContent
from src.infrastructure.browser import tistory_editor as te


def _stub_editor(monkeypatch, *, verify):
    noop = lambda *a, **k: True  # noqa: E731
    monkeypatch.setattr(te.time, "sleep", lambda *_: None)
    monkeypatch.setattr(te, "find_element", lambda *a, **k: "#title")
    monkeypatch.setattr(te, "render_tistory_html", lambda *a, **k: "<p>x</p>")
    monkeypatch.setattr(te, "_photo_uploader", lambda *a, **k: None)
    monkeypatch.setattr(te, "form_filler", SimpleNamespace(
        safe_click=noop, safe_type=noop, input_tags=noop))
    monkeypatch.setattr(te, "content_injector", SimpleNamespace(
        wait_for_wysiwyg_editor=noop, install_ajax_content_interceptor=noop,
        inject_html_content=noop, ensure_content_in_form=noop))
    monkeypatch.setattr(te, "_publish_via_api",
                        lambda *a, **k: ("https://b.tistory.com/77", "77"))
    monkeypatch.setattr(te, "publish_verifier", SimpleNamespace(verify_published_url=verify))


def _sb():
    return SimpleNamespace(open=lambda *_: None, set_window_size=lambda *_: None,
                           driver=SimpleNamespace(set_script_timeout=lambda *_: None))


def _post():
    return Post(row_index=2, keyword="k",
                content=PostContent(title="t", body_markdown="## 본문\n내용"))


def test_API_발행_후_검증_예외면_성공으로_돌려준다(monkeypatch):
    def boom(url):
        raise TimeoutError("verify timed out")

    _stub_editor(monkeypatch, verify=boom)

    result = te.publish_post(_sb(), _post(), "b")

    assert result.success is True
    assert result.url == "https://b.tistory.com/77" and result.entry_id == "77"
    assert result.warnings


def test_API_발행_전_예외는_실패(monkeypatch):
    _stub_editor(monkeypatch, verify=lambda url: 200)
    monkeypatch.setattr(te, "find_element", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("no editor")))

    result = te.publish_post(_sb(), _post(), "b")

    assert result.success is False
