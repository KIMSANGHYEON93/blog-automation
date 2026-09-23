"""티스토리 세션 쿠키 보존 — 로그인 횟수를 줄여 카카오 2FA 유발을 막는다.

2026-09-23 실측: 하루 브라우저 기동 7회에 2FA가 3회 떴다. 정상 운영은 하루 2회면
충분한데, 매 실행이 새 로그인을 하니 카카오 이상탐지에 걸린다.

티스토리 세션 쿠키(__T_, __T_SECURE)는 세션 쿠키라 브라우저를 닫으면 사라진다.
디스크에 보존했다가 다시 주입하면 서버 세션이 살아 있는 동안 로그인을 건너뛴다.

쿠키는 인증 자격증명이다 — 파일 권한과 저장 대상 필터를 테스트로 못 박는다.
"""
from __future__ import annotations

import json
import os
import time

from src.infrastructure.browser.session_store import (
    SessionStore,
    is_tistory_cookie,
    strip_expired,
)


def cookie(name="__T_", domain=".kimsanghyeon.tistory.com", expiry=None, **kw):
    c = {"name": name, "value": "v", "domain": domain, "path": "/"}
    if expiry is not None:
        c["expiry"] = expiry
    c.update(kw)
    return c


class TestCookieFilter:
    """카카오 쿠키까지 저장하면 유출 시 피해가 커진다 — 티스토리 것만 담는다."""

    def test_티스토리_도메인은_저장한다(self):
        assert is_tistory_cookie(cookie(domain=".kimsanghyeon.tistory.com"))
        assert is_tistory_cookie(cookie(domain="www.tistory.com"))

    def test_카카오_도메인은_제외한다(self):
        assert not is_tistory_cookie(cookie(domain=".kakao.com"))
        assert not is_tistory_cookie(cookie(domain="accounts.kakao.com"))

    def test_추적용_도메인도_제외한다(self):
        """tiara는 카카오 트래킹이라 로그인과 무관하다."""
        assert not is_tistory_cookie(cookie(domain=".tiara.tistory.com"))

    def test_도메인이_없으면_제외(self):
        assert not is_tistory_cookie({"name": "x", "value": "v"})


class TestExpiry:
    def test_만료된_쿠키는_버린다(self):
        past = int(time.time()) - 100
        assert strip_expired([cookie(expiry=past)], now=int(time.time())) == []

    def test_만료_전이면_남긴다(self):
        future = int(time.time()) + 3600
        assert len(strip_expired([cookie(expiry=future)], now=int(time.time()))) == 1

    def test_만료_없는_세션_쿠키는_남긴다(self):
        """__T_ 가 바로 이 경우다 — 서버가 만료를 쥐고 있다."""
        assert len(strip_expired([cookie()], now=int(time.time()))) == 1


class TestSessionStore:
    def test_저장하고_다시_읽는다(self, tmp_path):
        store = SessionStore(tmp_path / "session.json")
        store.save([cookie(name="__T_"), cookie(name="__T_SECURE")])
        assert {c["name"] for c in store.load()} == {"__T_", "__T_SECURE"}

    def test_티스토리_쿠키만_저장된다(self, tmp_path):
        store = SessionStore(tmp_path / "session.json")
        store.save([cookie(name="__T_"), cookie(name="_kau", domain=".kakao.com")])
        assert [c["name"] for c in store.load()] == ["__T_"]

    def test_파일_권한은_소유자만(self, tmp_path):
        """쿠키는 자격증명이다 — 같은 머신의 다른 사용자가 읽으면 안 된다."""
        path = tmp_path / "session.json"
        SessionStore(path).save([cookie()])
        assert oct(os.stat(path).st_mode)[-3:] == "600"

    def test_파일이_없으면_빈_리스트(self, tmp_path):
        assert SessionStore(tmp_path / "없음.json").load() == []

    def test_깨진_파일은_빈_리스트(self, tmp_path):
        """손상된 세션 때문에 발행이 멈추면 안 된다 — 그냥 재로그인한다."""
        path = tmp_path / "session.json"
        path.write_text("{깨진 JSON", encoding="utf-8")
        assert SessionStore(path).load() == []

    def test_만료된_쿠키는_읽을_때_걸러진다(self, tmp_path):
        path = tmp_path / "session.json"
        store = SessionStore(path)
        store.save([cookie(name="살아있음", expiry=int(time.time()) + 3600),
                    cookie(name="만료됨", expiry=int(time.time()) - 10)])
        assert [c["name"] for c in store.load()] == ["살아있음"]

    def test_저장할_게_없으면_파일을_만들지_않는다(self, tmp_path):
        path = tmp_path / "session.json"
        SessionStore(path).save([cookie(domain=".kakao.com")])
        assert not path.exists()

    def test_clear는_파일을_지운다(self, tmp_path):
        path = tmp_path / "session.json"
        store = SessionStore(path)
        store.save([cookie()])
        store.clear()
        assert not path.exists()
        assert store.load() == []

    def test_clear는_파일이_없어도_안_죽는다(self, tmp_path):
        SessionStore(tmp_path / "없음.json").clear()

    def test_저장은_디렉터리를_만든다(self, tmp_path):
        path = tmp_path / "깊은" / "경로" / "session.json"
        SessionStore(path).save([cookie()])
        assert path.exists()

    def test_저장_형식은_JSON_리스트(self, tmp_path):
        path = tmp_path / "session.json"
        SessionStore(path).save([cookie()])
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), list)
