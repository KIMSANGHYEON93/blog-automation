"""api_publisher — 수정(update) 호출이 새 글을 만들지 않는지 검증.

2026-04-08~2026-09-22: update_post가 항상 POST /manage/post.json을 호출해
Tistory가 매번 새 글을 만들었다(30건 이상 중복 발행, 시트 URL도 덮어씀).
에디터 번들 post-editor.min.js의 분기:
    method = (id === '0') ? 'post' : 'put'
    url    = (method === 'post') ? '/post.json' : '/post/<id>.json'
"""
from __future__ import annotations

import json

import pytest

from src.infrastructure.browser import api_publisher


class FakeDriver:
    """execute_async_script로 전달된 JS를 실행하는 대신 요청 형태만 기록한다."""

    def __init__(self, responder):
        self._responder = responder
        self.calls: list[dict] = []

    def set_script_timeout(self, _timeout):  # pragma: no cover - 무동작
        pass

    def execute_async_script(self, script, *args):
        entry_id = args[7] or "0"
        is_update = entry_id != "0"
        call = {
            "entry_id": entry_id,
            "method": "PUT" if is_update else "POST",
            "url": (
                f"/manage/post/{entry_id}.json" if is_update else "/manage/post.json"
            ),
            "published": args[9],
        }
        self.calls.append(call)
        return json.dumps(self._responder(call))


class FakeSB:
    """수정 화면의 window.Config.post.published 조회는 original_published를 돌려준다."""

    def __init__(self, responder, original_published="1759100000"):
        self.driver = FakeDriver(responder)
        self._original_published = original_published

    def execute_script(self, _script, *args):
        return self._original_published if args else None


def _ok(entry_id: str) -> dict:
    url = f"https://blog.tistory.com/{entry_id}"
    return {"status": 200, "success": True, "entryUrl": url, "entryId": entry_id}


class TestUpdateUsesPutEndpoint:
    def test_수정은_PUT_post_id_json(self):
        sb = FakeSB(lambda call: _ok(call["entry_id"]))
        result = api_publisher.call_tistory_post_api(
            sb, "blog", "제목", "<p>본문</p>", "", entry_id="252", max_retries=1,
        )
        assert result == ("https://blog.tistory.com/252", "252")
        assert sb.driver.calls[0]["method"] == "PUT"
        assert sb.driver.calls[0]["url"] == "/manage/post/252.json"

    def test_신규는_POST_post_json(self):
        sb = FakeSB(lambda _call: _ok("900"))
        result = api_publisher.call_tistory_post_api(
            sb, "blog", "제목", "<p>본문</p>", "", entry_id="0", max_retries=1,
        )
        assert result == ("https://blog.tistory.com/900", "900")
        assert sb.driver.calls[0]["method"] == "POST"
        assert sb.driver.calls[0]["url"] == "/manage/post.json"


class TestUpdateKeepsOriginalPublishDate:
    """published='1'은 '지금 발행' — 수정 때 보내면 발행일이 수정 시각으로 바뀐다."""

    def test_수정은_원래_발행시각을_보낸다(self):
        sb = FakeSB(lambda call: _ok(call["entry_id"]), original_published="1759100000")
        api_publisher.call_tistory_post_api(
            sb, "blog", "제목", "<p>본문</p>", "", entry_id="252", max_retries=1,
        )
        assert sb.driver.calls[0]["published"] == "1759100000"

    def test_원래_발행시각을_못_읽으면_수정하지_않는다(self):
        sb = FakeSB(lambda call: _ok(call["entry_id"]), original_published="")
        result = api_publisher.call_tistory_post_api(
            sb, "blog", "제목", "<p>본문</p>", "", entry_id="252", max_retries=1,
        )
        assert result is None
        assert sb.driver.calls == []

    def test_신규는_지금_발행(self):
        sb = FakeSB(lambda _call: _ok("900"), original_published="")
        api_publisher.call_tistory_post_api(
            sb, "blog", "제목", "<p>본문</p>", "", entry_id="0", max_retries=1,
        )
        assert sb.driver.calls[0]["published"] == "1"


class TestMismatchedEntryIsRejected:
    """Tistory는 잘못된 수정 요청을 오류 대신 '새 글'로 처리한다."""

    def test_다른_글_ID가_돌아오면_실패(self):
        sb = FakeSB(lambda _call: _ok("546"))  # 252를 요청했는데 546이 반환
        result = api_publisher.call_tistory_post_api(
            sb, "blog", "제목", "<p>본문</p>", "", entry_id="252", max_retries=1,
        )
        assert result is None, "중복 글 URL이 그대로 반환되면 시트가 덮어써진다"


@pytest.mark.parametrize(
    ("entry_id", "returned", "expected"),
    [
        ("0", ("https://blog.tistory.com/1", "1"), True),
        ("", ("https://blog.tistory.com/1", "1"), True),
        ("252", ("https://blog.tistory.com/252", "252"), True),
        ("252", ("https://blog.tistory.com/252", ""), True),
        ("252", ("https://blog.tistory.com/546", "546"), False),
        ("252", ("https://blog.tistory.com/546", ""), False),
    ],
)
def test_is_expected_entry(entry_id, returned, expected):
    assert api_publisher._is_expected_entry(returned, entry_id) is expected
