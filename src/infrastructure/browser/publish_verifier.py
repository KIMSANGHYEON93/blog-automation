"""publish_verifier — Post-publication verification, URL extraction, visibility fixing."""
from __future__ import annotations

import logging
import re
import time

from src.infrastructure.browser import form_filler
from src.infrastructure.browser.dom_selectors import (
    PUBLISH_CONFIRM_SELECTORS,
    find_element,
)

logger = logging.getLogger(__name__)


def check_publish_layer_opened(sb) -> str | None:
    """발행 설정 레이어가 열렸는지 확인. 열렸으면 감지된 셀렉터/텍스트, 아니면 None."""
    try:
        result: str | None = sb.execute_script("""
            // 발행 설정 레이어 DOM 존재 확인
            var indicators = [
                '#publish-btn', '.btn_publish', '#open-type-0',
                '.layer_post', '.layer_publish', '#publish-form',
                'input[name="visibility"]', 'input[name="openType"]',
                'label[for="open-type-0"]'
            ];
            for (var i = 0; i < indicators.length; i++) {
                var el = document.querySelector(indicators[i]);
                if (el) return indicators[i];
            }
            // 텍스트 기반: "공개", "비공개", "발행하기" (visible only)
            var all = document.querySelectorAll('label, button, a, span, div, input');
            for (var j = 0; j < all.length; j++) {
                var txt = all[j].textContent.trim();
                var rect = all[j].getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 &&
                    (txt === '공개' || txt === '발행하기' || txt === '비공개'
                     || txt === '보호' || txt === '발행')) {
                    return 'text:' + txt + ':' + all[j].tagName + '#' + all[j].id;
                }
            }
            return null;
        """)
        return result
    except Exception:
        return None


def click_publish_confirm_in_modal(sb, blog_name: str) -> str | None:
    """발행 설정 모달에서 발행 확인 버튼 클릭. 성공 시 entryUrl 반환."""

    def _after_publish(sb, blog_name: str) -> str | None:
        """발행 후 실제 글 URL 추출."""
        time.sleep(5)
        current_url: str = sb.get_current_url()
        if "/manage/newpost" in current_url:
            return None  # 아직 에디터 → 실패
        # /manage/posts/ 리다이렉트 → 가장 최근 글 URL 추출
        if "/manage/" in current_url:
            extracted = extract_published_url(sb, blog_name)
            if extracted:
                return extracted
            # fallback: /manage/posts 페이지에서 최신 글 링크 추출
            try:
                url: str | None = sb.execute_script("""
                    var links = document.querySelectorAll(
                        'a[href*="tistory.com/"]'
                    );
                    var pattern = /tistory\\.com\\/\\d+$/;
                    for (var i = 0; i < links.length; i++) {
                        if (pattern.test(links[i].href)) {
                            return links[i].href;
                        }
                    }
                    return null;
                """)
                if url:
                    return url
            except Exception:
                pass
            logger.warning(f"발행 URL 추출 실패, 관리 페이지: {current_url}")
            return current_url
        return current_url

    # CSS 셀렉터로 발행 확인 버튼 찾기
    confirm_sel = find_element(sb, PUBLISH_CONFIRM_SELECTORS, timeout=5)
    if confirm_sel:
        form_filler.safe_click(sb, confirm_sel)
        url = _after_publish(sb, blog_name)
        if url:
            return url

    # React fiber로 발행 확인 버튼 클릭
    try:
        result = sb.execute_script("""
            var btn = document.querySelector('#publish-btn');
            if (!btn) {
                var buttons = document.querySelectorAll('button');
                for (var i = 0; i < buttons.length; i++) {
                    var txt = buttons[i].textContent.trim();
                    if (txt === '발행하기' || txt === '발행') {
                        btn = buttons[i];
                        break;
                    }
                }
            }
            if (!btn) return 'no-btn';

            var keys = Object.keys(btn);
            var propsKey = keys.find(function(k) {
                return k.startsWith('__reactProps$');
            });
            if (propsKey && btn[propsKey] && btn[propsKey].onClick) {
                btn[propsKey].onClick(
                    new MouseEvent('click', {bubbles: true})
                );
                return 'react-clicked';
            }
            btn.click();
            return 'native-clicked';
        """)
        logger.info(f"발행 확인 버튼 결과: {result}")
        if result in ("react-clicked", "native-clicked"):
            url = _after_publish(sb, blog_name)
            if url:
                return url
    except Exception as e:
        logger.warning(f"발행 확인 버튼 클릭 예외: {e}")

    return None


def extract_published_url(sb, blog_name: str) -> str | None:
    """발행 후 관리 페이지에서 방금 발행한 글의 실제 URL을 추출."""
    try:
        time.sleep(2)
        # 관리 페이지에서 해당 블로그의 첫 번째 글 링크 추출
        url: str | None = sb.execute_script("""
            var blogName = arguments[0];
            var pattern = new RegExp(
                'https://' + blogName + '\\\\.tistory\\\\.com/\\\\d+$'
            );
            var links = document.querySelectorAll('a');
            for (var i = 0; i < links.length; i++) {
                var href = links[i].href;
                if (href && pattern.test(href)) {
                    return href;
                }
            }
            return null;
        """, blog_name)
        if url:
            return url
        logger.warning("관리 페이지에서 글 URL을 찾지 못함")
    except Exception as e:
        logger.warning(f"발행 URL 추출 중 오류: {e}")
    return None


def verify_published_url(url: str, timeout: int = 10) -> int:
    """발행된 URL에 HTTP HEAD 요청으로 공개 상태 확인.

    Returns:
        HTTP 상태 코드 (200=공개, 403=비공개, 404=미존재, 0=네트워크오류).
    """
    import urllib.error
    import urllib.request

    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header(
            "User-Agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as exc:
        logger.debug(f"URL 검증 요청 실패: {exc}")
        return 0


def extract_post_id(url: str) -> str | None:
    """티스토리 URL에서 게시글 ID 추출. e.g. '.../211' → '211'."""
    m = re.search(r"/(\d+)$", url)
    return m.group(1) if m else None


def fix_post_visibility(sb, blog_name: str, published_url: str) -> bool:
    """비공개로 발행된 글을 공개(visibility=20)로 수정.

    Tistory 내부 API: POST /manage/post.json (id 포함 시 수정 동작).
    """
    import json as json_mod

    post_id = extract_post_id(published_url)
    if not post_id:
        logger.warning(f"게시글 ID 추출 실패: {published_url}")
        return False

    logger.info(f"비공개→공개 복구 시도: post_id={post_id}")

    try:
        result_json = sb.driver.execute_async_script(
            """
            var callback = arguments[arguments.length - 1];
            var postId = arguments[0];
            var blogName = arguments[1];

            var manageUrl = '';
            if (window.appInfo && window.appInfo.manageUrl) {
                manageUrl = window.appInfo.manageUrl;
            } else {
                manageUrl = 'https://' + blogName + '.tistory.com/manage';
            }

            var url = manageUrl + '/post.json';

            // 최소 수정 요청: ID + visibility만 전송
            var payload = {
                id: postId,
                visibility: '20',
                published: '1'
            };

            fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(payload),
                credentials: 'include'
            })
            .then(function(resp) {
                return resp.text().then(function(text) {
                    return { status: resp.status, text: text };
                });
            })
            .then(function(r) {
                callback(JSON.stringify({
                    success: r.status >= 200 && r.status < 300,
                    status: r.status,
                    response: r.text.substring(0, 500)
                }));
            })
            .catch(function(e) {
                callback(JSON.stringify({
                    success: false, error: 'fetch:' + e.message
                }));
            });
        """,
            post_id,
            blog_name,
        )

        if result_json:
            result = json_mod.loads(result_json)
            if result.get("success"):
                logger.info(
                    f"visibility 수정 API 성공: post_id={post_id}"
                )
                time.sleep(3)  # CDN 캐시 전파 대기
                return True
            logger.warning(
                f"visibility 수정 API 실패 "
                f"(status={result.get('status')}): "
                f"{result.get('response', '')[:200]}"
            )
        return False
    except Exception as e:
        logger.warning(f"visibility 수정 예외: {e}")
        return False


def verify_faq_schema(url: str, timeout: int = 10) -> bool:
    """발행된 URL의 HTML에서 FAQPage LD+JSON 존재 여부 확인."""
    import urllib.request

    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header(
            "User-Agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        return '"FAQPage"' in html and '"application/ld+json"' in html
    except Exception as exc:
        logger.debug(f"FAQ 스키마 검증 실패: {exc}")
        return False
