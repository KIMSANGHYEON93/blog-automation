"""공식 문서 캡처 — 글의 참고자료 주소를 로그인 없는 헤드리스 브라우저로 찍어 사진으로 저장한다.

캡처는 '이 정보를 공식 문서에서 확인했다'는 증거라, 없는 페이지(404·홈으로 튕김)를 찍으면
신뢰를 오히려 깎는다. 그래서 먼저 열어 보고 같은 페이지가 정상으로 열릴 때만 찍는다.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import requests  # type: ignore[import-untyped]

from src.infrastructure.browser.naver.images import save_photo

logger = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/130 Safari/537.36")
WINDOW_SIZE = (1280, 900)
PAGE_LOAD_TIMEOUT = 30  # 초 — 로드가 안 끝나면 멈추고 그대로 찍는다(editor._open과 같은 이유)


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_same_site(original: str, final: str) -> bool:
    """리다이렉트 뒤에도 같은 페이지 쪽인지. 상위 도메인·첫 화면으로 튕기면 없는 페이지로 본다."""
    a, b = _host(original), _host(final)
    if not (a == b or b.endswith("." + a)):
        return False
    return not (urlparse(original).path.strip("/") and not urlparse(final).path.strip("/"))


def _reachable(url: str) -> bool:
    try:
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=15, allow_redirects=True)
    except Exception as e:
        logger.warning(f"공식 문서 열기 실패 — 건너뜀: {url} ({e})")
        return False
    if resp.status_code != 200 or not is_same_site(url, resp.url):
        logger.warning(f"공식 문서가 정상으로 열리지 않음 — 건너뜀: {url} "
                       f"→ {resp.status_code} {resp.url}")
        return False
    return True


def capture_official_docs(urls: list[str], directory: str | Path) -> list[tuple[str, str]]:
    """열리는 주소만 찍어 (주소, 저장한 파일 이름) 목록을 돌려준다. 실패한 주소는 빠진다."""
    reachable = [u for u in urls if _reachable(u)]
    if not reachable:
        return []
    from seleniumbase import SB

    captured: list[tuple[str, str]] = []
    # 네이버 발행 브라우저(.browser_data_naver)와 섞이지 않게 로그인 없는 임시 프로필로 연다
    with SB(headless=True) as sb:
        sb.set_window_size(*WINDOW_SIZE)
        sb.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        for url in reachable:
            try:
                try:
                    sb.open(url)
                except Exception as e:
                    if "timed out" not in str(e).lower():
                        raise
                    sb.execute_script("window.stop();")
                time.sleep(2)  # 글꼴·첫 화면 이미지
                name = save_photo(sb.driver.get_screenshot_as_png(), directory)
                if name:
                    captured.append((url, name))
            except Exception as e:
                logger.warning(f"공식 문서 캡처 실패 — 건너뜀: {url} ({e})")
    return captured
