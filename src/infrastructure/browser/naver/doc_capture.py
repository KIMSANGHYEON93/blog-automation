"""공식 문서 캡처 — 글의 참고자료 주소를 로그인 없는 헤드리스 브라우저로 찍어 사진으로 저장한다.

캡처는 '이 정보를 공식 문서에서 확인했다'는 증거라, 없는 페이지(404·홈으로 튕김)를 찍으면
신뢰를 오히려 깎는다. 그래서 먼저 열어 보고 같은 페이지가 정상으로 열릴 때만 찍는다.

보안(SSRF): 주소는 LLM이 쓴 참고자료라 내부망 주소가 섞일 수 있다. http/https만, 호스트의 IP·DNS
해석 결과 전부가 공인 주소일 때만 요청하고, 리다이렉트는 자동으로 따르지 않고 단계마다 같은 검사를
한다(사전 확인은 stream으로 본문을 받지 않는다). 브라우저가 도착한 주소도 다시 검사해
아니면 찍지 않는다.
브라우저는 주소마다 따로 열고, 그 호스트를 검사한 IP로 고정한다(--host-resolver-rules) — 검사와 접속
사이 DNS 응답이 바뀌는(재바인딩) 틈을 닫는다. 페이지가 내부 주소로 보내는 fetch·이미지 요청은
Chrome 기본 Local Network Access가 막는다(Chrome 156 실측, 2026-10-29 — CDP setBlockedURLs는
효과가 없어 쓰지 않음).
한계: 페이지 스크립트가 최상위 화면을 내부 주소로 옮기면 GET 한 번은 나간다(응답은 못 읽고,
도착 주소 검사가 캡처를 버린다).
참고자료는 제품 도움말 등 임의 도메인이라 허용 목록으로 좁히지 않았다.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import requests  # type: ignore[import-untyped]

from src.infrastructure.browser.naver.images import save_photo

logger = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/130 Safari/537.36")
WINDOW_SIZE = (1280, 900)
PAGE_LOAD_TIMEOUT = 30  # 초 — 로드가 안 끝나면 멈추고 그대로 찍는다(editor._open과 같은 이유)
REQUEST_TIMEOUT = (5, 15)  # 초 — 연결, 읽기
MAX_REDIRECTS = 3
Resolver = Callable[[str], "list[str]"]


def _system_resolve(host: str) -> list[str]:
    return [str(info[4][0]) for info in socket.getaddrinfo(host, None)]


def is_public_ip(address: str) -> bool:
    """루프백·사설·링크로컬(메타데이터)·CGNAT·멀티캐스트·예약·6to4/Teredo가 아니면 True.

    IPv4-mapped IPv6는 안의 IPv4로 판단한다.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return is_public_ip(str(ip.ipv4_mapped))
        if ip.sixtofour is not None or ip.teredo is not None or ip.is_site_local:
            return False
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def _literal_ip(host: str) -> str | None:
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    try:  # 10진·8진·16진 IPv4 표기(2130706433, 0x7f.1) — 브라우저·libc가 같은 IP로 해석한다
        return socket.inet_ntoa(socket.inet_aton(host))
    except OSError:
        return None


def unsafe_reason(url: str, resolver: Resolver = _system_resolve) -> str | None:
    """요청하면 안 되는 주소면 사유, 괜찮으면 None."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname
    except ValueError:
        return "URL 형식 오류"
    if parsed.scheme not in ("http", "https"):
        return f"허용하지 않는 프로토콜 {parsed.scheme}"
    if parsed.username or parsed.password:
        return "계정 정보가 든 URL"
    if not host:
        return "호스트 없음"
    literal = _literal_ip(host)
    if literal is not None:
        return None if is_public_ip(literal) else f"내부·예약 주소 {literal}"
    try:
        addresses = resolver(host)
    except OSError as e:
        return f"DNS 해석 실패 ({e})"
    if not addresses:
        return "DNS 응답 없음"
    bad = [a for a in addresses if not is_public_ip(a)]
    return f"내부 주소로 해석됨 {bad[0]}" if bad else None


def landing_ok(original: str, current: str, resolver: Resolver = _system_resolve) -> bool:
    """브라우저가 실제로 도착한 주소가 안전하고 같은 페이지 쪽인지."""
    return unsafe_reason(current, resolver) is None and is_same_site(original, current)


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_same_site(original: str, final: str) -> bool:
    """리다이렉트 뒤에도 같은 페이지 쪽인지. 상위 도메인·첫 화면으로 튕기면 없는 페이지로 본다."""
    a, b = _host(original), _host(final)
    if not (a == b or b.endswith("." + a)):
        return False
    return not (urlparse(original).path.strip("/") and not urlparse(final).path.strip("/"))


def reachable_url(
    url: str, *, get: Callable[..., Any] = requests.get, resolver: Resolver = _system_resolve,
) -> str | None:
    """리다이렉트를 단계마다 검사하며 따라가 200으로 열리는 같은 사이트 주소를 돌려준다.

    아니면 None.
    """
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        reason = unsafe_reason(current, resolver)
        if reason:
            logger.warning(f"공식 문서 주소 차단 — 건너뜀: {current} ({reason})")
            return None
        try:
            resp = get(current, headers={"User-Agent": _UA}, timeout=REQUEST_TIMEOUT,
                       allow_redirects=False, stream=True)
        except Exception as e:
            logger.warning(f"공식 문서 열기 실패 — 건너뜀: {current} ({e})")
            return None
        try:
            location = resp.headers.get("Location")
            if resp.is_redirect and location:
                current = urljoin(current, location)
                continue
            if resp.status_code != 200 or not is_same_site(url, current):
                logger.warning(f"공식 문서가 정상으로 열리지 않음 — 건너뜀: {url} "
                               f"→ {resp.status_code} {current}")
                return None
            return current
        finally:
            resp.close()
    logger.warning(f"공식 문서 리다이렉트 {MAX_REDIRECTS}회 초과 — 건너뜀: {url}")
    return None


def pinned_resolver_rule(url: str, resolver: Resolver = _system_resolve) -> str | None:
    """브라우저가 이 호스트를 방금 검사한 IP로만 접속하게 하는 --host-resolver-rules 값.

    해석은 한 번만 하고 그 결과 전부가 공인일 때만 고정한다. IP 주소 자체면 고정할 게 없어
    빈 문자열, 내부·해석 실패면 None(찍지 않는다). IPv4를 먼저 쓴다.
    """
    host = urlparse(url).hostname or ""
    literal = _literal_ip(host)
    if literal is not None:
        return "" if is_public_ip(literal) else None
    try:
        addresses = resolver(host)
    except OSError:
        return None
    if not addresses or not all(is_public_ip(a) for a in addresses):
        return None
    ipv4 = [a for a in addresses if ":" not in a]
    return f"MAP {host} {ipv4[0] if ipv4 else f'[{addresses[0]}]'}"


def capture_official_docs(urls: list[str], directory: str | Path) -> list[tuple[str, str]]:
    """열리는 주소만 찍어 (주소, 저장한 파일 이름) 목록을 돌려준다. 실패한 주소는 빠진다."""
    captured: list[tuple[str, str]] = []
    for url in urls:
        final = reachable_url(url)
        rule = pinned_resolver_rule(final) if final else None
        if final is None or rule is None:
            continue
        name = _capture_one(url, final, rule, directory)
        if name:
            captured.append((url, name))
    return captured


def _capture_one(url: str, final: str, rule: str, directory: str | Path) -> str | None:
    """IP를 고정한 새 브라우저로 한 주소를 찍는다. 고정 규칙이 주소마다 달라 따로 연다."""
    from seleniumbase import SB

    # 네이버 발행 브라우저(.browser_data_naver)와 섞이지 않게 로그인 없는 임시 프로필로 연다.
    # SB는 chromium_arg를 쉼표로 나누므로 규칙은 하나만 넣는다
    args = {"chromium_arg": f"--host-resolver-rules={rule}"} if rule else {}
    try:
        with SB(headless=True, **args) as sb:
            sb.set_window_size(*WINDOW_SIZE)
            sb.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            try:
                sb.open(final)  # 검사를 마친 마지막 주소를 연다
            except Exception as e:
                if "timed out" not in str(e).lower():
                    raise
                sb.execute_script("window.stop();")
            time.sleep(2)  # 글꼴·첫 화면 이미지
            landed = sb.get_current_url()
            if not landing_ok(url, landed):
                logger.warning(f"공식 문서가 다른 곳으로 이동 — 캡처 버림: {url} → {landed}")
                return None
            return save_photo(sb.driver.get_screenshot_as_png(), directory)
    except Exception as e:
        logger.warning(f"공식 문서 캡처 실패 — 건너뜀: {url} ({e})")
        return None
