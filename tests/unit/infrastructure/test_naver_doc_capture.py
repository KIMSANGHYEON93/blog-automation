"""공식 문서 캡처 — 열리지 않거나 다른 사이트로 넘어가는 주소, 내부망 주소는 캡처하지 않는다.

네트워크는 쓰지 않는다: 가짜 resolver·가짜 requests.get만 쓴다.
"""
from __future__ import annotations

import pytest

from src.infrastructure.browser.naver import doc_capture
from src.infrastructure.browser.naver.doc_capture import (
    is_public_ip,
    is_same_site,
    landing_ok,
    reachable_url,
    unsafe_reason,
)

PUBLIC = "93.184.216.34"


def public_resolver(host: str) -> list[str]:
    return [PUBLIC]


class FakeResponse:
    def __init__(self, status: int, location: str | None = None) -> None:
        self.status_code = status
        self.headers = {"Location": location} if location else {}
        self.is_redirect = location is not None and 300 <= status < 400
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeGet:
    def __init__(self, routes: dict[str, FakeResponse | Exception]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        r = self.routes[url]
        if isinstance(r, Exception):
            raise r
        return r


def test_같은_사이트로의_이동은_허용():
    assert is_same_site("https://www.canva.com/help", "https://canva.com/ko_kr/help/")
    assert is_same_site("https://support.google.com/gemini", "https://support.google.com/gemini/?hl=ko")


def test_다른_사이트로_넘어가면_거부():
    # 존재하지 않는 페이지가 로그인·홈·다른 도메인으로 튕기는 경우
    assert not is_same_site("https://learn.chatgpt.com/docs/prompting", "https://openai.com/")


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.0.0.1", "172.16.5.4", "192.168.0.1", "169.254.169.254", "100.64.0.1",
    "0.0.0.0", "224.0.0.1", "255.255.255.255", "::1", "::", "::ffff:127.0.0.1", "fe80::1",
    "fc00::1", "ff02::1", "2002:7f00:1::1", "2001:db8::1", "fec0::1", "not-an-ip",
])
def test_내부_예약_주소는_공인_아님(ip):
    assert not is_public_ip(ip)


@pytest.mark.parametrize("ip", [PUBLIC, "8.8.8.8", "2606:4700::1111"])
def test_공인_주소(ip):
    assert is_public_ip(ip)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://10.0.0.1/admin", "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "http://[::ffff:127.0.0.1]/",
    "http://0.0.0.0/", "http://2130706433/", "http://0x7f.1/", "http://017700000001/",
    "ftp://example.org/", "file:///etc/passwd", "https://user:pw@example.org/", "https:///nohost",
])
def test_내부_주소_형식_오류_URL은_거부(url):
    assert unsafe_reason(url, resolver=public_resolver) is not None


def test_DNS가_내부_IP로_해석되면_거부():
    assert unsafe_reason("https://a.example.org/", resolver=lambda h: [PUBLIC, "10.0.0.5"])
    assert unsafe_reason("http://localhost:5678/", resolver=lambda h: ["127.0.0.1"])
    assert unsafe_reason("https://a.example.org/", resolver=lambda h: [])
    assert unsafe_reason("https://a.example.org/", resolver=public_resolver) is None


def test_DNS_해석_실패는_거부():
    def fail(host: str) -> list[str]:
        raise OSError("nodename nor servname provided")

    assert unsafe_reason("https://nope.example.org/", resolver=fail)


def test_내부_주소는_요청하지_않는다():
    get = FakeGet({})
    assert reachable_url("http://169.254.169.254/", get=get, resolver=public_resolver) is None
    assert get.calls == []


def test_리다이렉트는_자동으로_따르지_않고_내부로_가면_거부():
    get = FakeGet({"https://a.example.org/doc": FakeResponse(302, "http://127.0.0.1:5678/")})
    assert reachable_url("https://a.example.org/doc", get=get, resolver=public_resolver) is None
    assert len(get.calls) == 1
    kwargs = get.calls[0][1]
    assert kwargs["allow_redirects"] is False
    assert kwargs["stream"] is True  # 본문을 내려받지 않는다


def test_공인_주소_리다이렉트는_단계마다_검사하며_따른다():
    get = FakeGet({
        "https://a.example.org/doc": FakeResponse(301, "/doc/"),
        "https://a.example.org/doc/": FakeResponse(200),
    })
    assert reachable_url("https://a.example.org/doc", get=get,
                         resolver=public_resolver) == "https://a.example.org/doc/"
    assert all(kw["allow_redirects"] is False for _, kw in get.calls)


def test_리다이렉트_상한을_넘으면_거부():
    routes: dict[str, FakeResponse | Exception] = {
        f"https://a.example.org/{i}": FakeResponse(302, f"/{i + 1}") for i in range(10)
    }
    get = FakeGet(routes)
    assert reachable_url("https://a.example.org/0", get=get, resolver=public_resolver) is None
    assert len(get.calls) == doc_capture.MAX_REDIRECTS + 1


def test_다른_사이트로_튕기거나_200이_아니면_거부():
    get = FakeGet({
        "https://a.example.org/x": FakeResponse(302, "https://b.example.org/"),
        "https://b.example.org/": FakeResponse(200),
        "https://a.example.org/404": FakeResponse(404),
        "https://a.example.org/err": ConnectionError("reset"),
    })
    for url in ("https://a.example.org/x", "https://a.example.org/404", "https://a.example.org/err"):
        assert reachable_url(url, get=get, resolver=public_resolver) is None


def test_브라우저가_도착한_주소도_다시_검사한다():
    assert landing_ok("https://a.example.org/doc", "https://a.example.org/doc/", public_resolver)
    assert not landing_ok("https://a.example.org/doc", "http://10.0.0.1/", public_resolver)
    assert not landing_ok("https://a.example.org/doc", "https://a.example.org/doc",
                          lambda h: ["192.168.0.10"])
