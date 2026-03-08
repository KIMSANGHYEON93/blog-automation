"""TistoryEditor — Tistory blog editor automation (2026-03-02 updated).

변경 이력:
  2026-03-02 — 일일 발행 제한 감지 + 배치 중단 (DailyPublishLimitError)
  2026-03-02 — 발행 후 HTTP 검증 + 비공개 자동 복구 (_verify / _fix_post_visibility)
  2026-03-01 — MD→HTML 변환: 마크다운 모드 대신 WYSIWYG 모드에서 HTML 주입 (방향 A)
  2026-02-28 — 비공개→공개 발행 전환
"""
from __future__ import annotations

import logging
import random as _rnd
import re
import time

import markdown as md_lib

from src.domain.entities.post import Post
from src.domain.exceptions import DailyPublishLimitError
from src.domain.value_objects.publish_result import PublishResult
from src.infrastructure.browser.dom_selectors import (
    CONTENT_AREA_SELECTORS,
    EDITOR_PATH,
    MARKDOWN_MODE_SELECTORS,
    MODE_CONFIRM_SELECTORS,
    MODE_SWITCH_BUTTON_SELECTORS,
    PUBLISH_CONFIRM_SELECTORS,
    TAG_INPUT_SELECTORS,
    TINYMCE_IFRAME_SELECTORS,
    TITLE_SELECTORS,
    find_element,
)
from src.infrastructure.seo.html_optimizer import optimize_html

logger = logging.getLogger(__name__)

_DAILY_LIMIT_PATTERN = "최대 15개까지"

# Tistory 카테고리 이름 → ID 매핑 (관리자 페이지에서 확인)
CATEGORY_MAP: dict[str, str] = {
    "용어": "991463",        # 배운것/용어정리
    "비교": "966384",        # 배운것
    "에러": "966384",        # 배운것
    "트러블슈팅": "966384",  # 배운것
    "가이드": "966384",      # 배운것
    "트렌드": "966384",      # 배운것
}


def _resolve_category_id(category_name: str) -> str:
    """카테고리 이름을 Tistory 카테고리 ID로 변환. 매칭 실패 시 '0'(미분류)."""
    if not category_name:
        return "0"
    name = category_name.strip()
    if name in CATEGORY_MAP:
        return CATEGORY_MAP[name]
    # 부분 매칭 시도
    name_lower = name.lower()
    for key, cid in CATEGORY_MAP.items():
        if key.lower() in name_lower or name_lower in key.lower():
            return cid
    return "0"


def _extract_first_image_url(html: str) -> str:
    """HTML 본문에서 첫 번째 <img> src URL 추출 (대표이미지 자동 선택용).

    - data: URI, 상대 경로는 건너뜀
    - http/https URL만 반환, 없으면 빈 문자열
    """
    if not html:
        return ""
    for match in re.finditer(r'<img\s[^>]*?src=["\']([^"\']+)["\']', html):
        src = match.group(1).strip()
        if src.startswith("data:"):
            continue
        if not src.startswith(("http://", "https://")):
            continue
        return src
    return ""


def _safe_click(sb, selector: str) -> bool:
    """요소 클릭 — 네이티브 시도 후 JS fallback (full mouse event sequence)."""
    # 방법 1: 네이티브 SeleniumBase 클릭
    try:
        sb.click(selector)
        logger.debug(f"네이티브 클릭 성공: {selector}")
        return True
    except Exception:
        pass
    # 방법 2: JS — full mouse event sequence (mousedown → mouseup → click)
    try:
        js = (
            f"var el = document.querySelector('{selector}');"
            "if (!el) return false;"
            "var o = {bubbles:true, cancelable:true, view:window};"
            "el.dispatchEvent(new MouseEvent('mousedown', o));"
            "el.dispatchEvent(new MouseEvent('mouseup', o));"
            "el.dispatchEvent(new MouseEvent('click', o));"
            "return true;"
        )
        clicked = sb.execute_script(js)
        if clicked:
            logger.debug(f"JS MouseEvent 클릭: {selector}")
            return True
    except Exception:
        pass
    # 방법 3: JS — el.click() 단순 호출
    try:
        clicked = sb.execute_script(
            f"var el = document.querySelector('{selector}');"
            "if (el) { el.click(); return true; } return false;"
        )
        if clicked:
            logger.debug(f"JS el.click() 클릭: {selector}")
            return True
    except Exception:
        pass
    logger.warning(f"클릭 실패: {selector}")
    return False


def _safe_type(sb, selector: str, text: str) -> bool:
    """요소에 텍스트 입력 — 네이티브 시도 후 JS fallback (React 호환)."""
    try:
        sb.type(selector, text)
        return True
    except Exception:
        pass
    # JS fallback: React nativeInputValueSetter로 React state 동기화
    try:
        result = sb.execute_script("""
            var el = document.querySelector(arguments[0]);
            if (!el) return false;
            el.focus();
            // React nativeInputValueSetter 사용 (React 내부 state 동기화)
            var tagName = el.tagName.toLowerCase();
            var proto = tagName === 'textarea'
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
            var setter = Object.getOwnPropertyDescriptor(proto, 'value');
            if (setter && setter.set) {
                setter.set.call(el, arguments[1]);
            } else {
                el.value = arguments[1];
            }
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
        """, selector, text)
        if result:
            logger.debug(f"JS nativeInputValueSetter 입력: {selector}")
            return True
    except Exception:
        pass
    logger.warning(f"텍스트 입력 실패: {selector}")
    return False


def _check_publish_layer_opened(sb) -> str | None:
    """발행 설정 레이어가 열렸는지 확인. 열렸으면 감지된 셀렉터/텍스트, 아니면 None."""
    try:
        return sb.execute_script("""
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
    except Exception:
        return None


def publish_post(sb, post: Post, blog_name: str) -> PublishResult:
    """티스토리 에디터에 포스트 발행. PublishResult 반환."""
    try:
        if post.content is None or not post.content.body_markdown:
            return PublishResult.fail("포스트 콘텐츠가 없음")

        content = post.content
        body_markdown: str = content.body_markdown or ""

        # 브라우저 창 크기 설정 (에디터 사이드바 가시성 확보)
        import contextlib

        with contextlib.suppress(Exception):
            sb.set_window_size(1920, 1080)

        # async script timeout 확장 (Fetch API 호출 대기용, 기본 30초 → 120초)
        with contextlib.suppress(Exception):
            sb.driver.set_script_timeout(120)

        # 에디터 페이지 열기 (같은 URL 재방문 시 강제 리로드)
        write_url = f"https://{blog_name}.tistory.com{EDITOR_PATH}"
        fresh_url = f"{write_url}?_t={int(time.time())}{_rnd.randint(0, 999)}"
        sb.open(fresh_url)
        time.sleep(5)

        # 에디터 로드 대기 (제목 입력창 DOM 존재 확인)
        title_sel = find_element(sb, TITLE_SELECTORS, timeout=15)
        if not title_sel:
            return PublishResult.fail("제목 입력창을 찾을 수 없음")

        # 제목 입력 (JS fallback 포함)
        title_text = content.title_or_fallback(post.keyword)
        _safe_click(sb, title_sel)
        if not _safe_type(sb, title_sel, title_text):
            return PublishResult.fail("제목 입력 실패")
        time.sleep(0.5)

        # --- MD→HTML 변환 (방향 A: Python 측 변환 후 WYSIWYG 모드 주입) ---
        html_body = convert_markdown_to_html(body_markdown)

        # 이미지 lazy loading 적용
        html_body = _add_lazy_loading(html_body)

        # 외부 링크에 nofollow/noopener 속성 추가
        html_body = _add_nofollow_to_external_links(html_body, blog_name)

        # 내부 링크 자동 삽입 (published 매핑이 있으면)
        internal_link_map = post.internal_link_map
        if internal_link_map:
            from src.infrastructure.seo.internal_linker import (
                inject_internal_links,
            )

            class _LinkPost:
                def __init__(self, kw, url):
                    self.keyword = kw
                    self.published_url = url

            link_posts = [
                _LinkPost(kw, url) for kw, url in internal_link_map.items()
            ]
            keywords = content.internal_keyword_list()
            prev_len = len(html_body)
            html_body = inject_internal_links(html_body, keywords, link_posts)
            logger.info(
                f"내부 링크 삽입: keywords={len(keywords)}, "
                f"published={len(link_posts)}, "
                f"body: {prev_len}→{len(html_body)}자"
            )

        # HTML 변환 검증
        if not validate_html(html_body):
            logger.warning("HTML 변환 검증 실패 — 그대로 진행")

        # FAQ LD+JSON 스키마 주입 (HTML 본문 하단에 추가)
        faq_ld_json = content.faq_ld_json() if hasattr(content, 'faq_ld_json') else ""
        if faq_ld_json:
            html_body = _append_faq_schema(html_body, faq_ld_json)

        # 반응형 + 성능 최적화 (img lazy/decoding, iframe lazy, preconnect)
        html_body = optimize_html(html_body)

        # [마크다운 모드 전환 — 비활성화: WYSIWYG 기본모드 사용]
        # sb.execute_script("window.confirm = function() { return true; };")
        # _switch_to_markdown_mode(sb)
        # time.sleep(2)

        # WYSIWYG 에디터 로드 대기
        _wait_for_wysiwyg_editor(sb)

        # AJAX 인터셉터 설치 (save/publish 요청에 빈 content → 실제 HTML 교체)
        _install_ajax_content_interceptor(sb, html_body)

        # HTML 본문 주입 (WYSIWYG 모드: TinyMCE / iframe / textarea)
        if not _inject_html_content(sb, html_body):
            return PublishResult.fail("HTML 본문 주입 실패")
        time.sleep(2)

        # 태그 입력
        if content.tags:
            _input_tags(sb, content.tag_list())
            time.sleep(1)

        # 메타 설명(meta description) 주입
        if content.meta_description:
            _inject_meta_description(sb, content.meta_description)
            time.sleep(0.5)

        # 저장 전 콘텐츠 동기화 확인
        _ensure_content_in_form(sb, html_body)

        # 직접 API 호출로 발행 (UI 버튼 클릭 대신)
        api_result = _publish_via_api(sb, blog_name, content, html_body, post)
        if not api_result:
            return PublishResult.fail("API 발행 실패 — 모든 방법 실패")

        published_url, entry_id = api_result
        logger.info(f"API 발행 완료: {post.keyword} → {published_url} (id={entry_id})")

        # --- 발행 후 공개 상태 검증 ---
        http_code = _verify_published_url(published_url)
        if http_code == 200:
            logger.info(f"공개 검증 성공 (200): {published_url}")
            # FAQ 스키마 검증 (경고 로그만, 실패 안 함)
            faq_ld_json = content.faq_ld_json() if hasattr(content, 'faq_ld_json') else ""
            if faq_ld_json:
                has_faq = _verify_faq_schema(published_url)
                if has_faq:
                    logger.info(f"FAQ 스키마 검증 성공: {published_url}")
                else:
                    logger.warning(f"FAQ 스키마 미발견 (수동 확인 필요): {published_url}")
            return PublishResult.ok(published_url, entry_id=entry_id)

        if http_code in (403, 404):
            logger.warning(
                f"발행 URL 비공개 감지 ({http_code}): {published_url}"
            )
            # 게시글 ID 추출 후 visibility 수정 시도
            fixed = _fix_post_visibility(sb, blog_name, published_url)
            if fixed:
                recheck = _verify_published_url(published_url)
                if recheck == 200:
                    logger.info(
                        f"비공개→공개 복구 성공: {published_url}"
                    )
                    return PublishResult.ok(published_url, entry_id=entry_id)
                logger.warning(
                    f"비공개→공개 복구 후에도 {recheck}: {published_url}"
                )
            # 복구 실패해도 URL은 반환 (시트에 기록용)
            logger.warning(
                f"비공개 상태로 발행됨 (수동 확인 필요): {published_url}"
            )
            return PublishResult.ok(published_url, entry_id=entry_id)

        # 기타 상태 코드 (5xx 등) — 일단 성공으로 기록
        logger.warning(f"발행 URL 검증 코드 {http_code}: {published_url}")
        return PublishResult.ok(published_url, entry_id=entry_id)

    except Exception as e:
        logger.error(f"발행 실패: {post.keyword} — {e}")
        return PublishResult.fail(str(e))


def update_post(sb, post: Post, blog_name: str) -> PublishResult:
    """기존 발행 글 수정. entry_id를 사용하여 Tistory API로 업데이트."""
    try:
        if not post.entry_id:
            return PublishResult.fail("entry_id 없음 — 수정 불가")
        if post.content is None or not post.content.body_markdown:
            return PublishResult.fail("포스트 콘텐츠가 없음")

        content = post.content
        body_markdown: str = content.body_markdown or ""

        # 에디터 페이지 열기 (API 컨텍스트 확보용)
        import contextlib

        with contextlib.suppress(Exception):
            sb.set_window_size(1920, 1080)

        # async script timeout 확장 (Fetch API 호출 대기용, 기본 30초 → 120초)
        with contextlib.suppress(Exception):
            sb.driver.set_script_timeout(120)

        write_url = f"https://{blog_name}.tistory.com{EDITOR_PATH}"
        fresh_url = f"{write_url}?_t={int(time.time())}{_rnd.randint(0, 999)}"
        sb.open(fresh_url)
        time.sleep(5)

        # MD→HTML 변환 (publish_post와 동일 파이프라인)
        html_body = convert_markdown_to_html(body_markdown)
        html_body = _add_lazy_loading(html_body)
        html_body = _add_nofollow_to_external_links(html_body, blog_name)

        # 내부 링크 자동 삽입
        internal_link_map = post.internal_link_map
        if internal_link_map:
            from src.infrastructure.seo.internal_linker import (
                inject_internal_links,
            )

            class _LinkPost:
                def __init__(self, kw, url):
                    self.keyword = kw
                    self.published_url = url

            link_posts = [
                _LinkPost(kw, url) for kw, url in internal_link_map.items()
            ]
            keywords = content.internal_keyword_list()
            html_body = inject_internal_links(html_body, keywords, link_posts)

        # FAQ LD+JSON 스키마 주입
        faq_ld_json = content.faq_ld_json() if hasattr(content, 'faq_ld_json') else ""
        if faq_ld_json:
            html_body = _append_faq_schema(html_body, faq_ld_json)

        # 반응형 + 성능 최적화
        html_body = optimize_html(html_body)

        # API 호출로 수정 (entry_id 전달)
        title = content.title_or_fallback(post.keyword)
        tags = ",".join(content.tag_list()) if content.tags else ""
        thumbnail_url = content.thumbnail_url if content.thumbnail_url else ""
        if not thumbnail_url:
            thumbnail_url = _extract_first_image_url(html_body)
        category_id = _resolve_category_id(post.category)

        api_result = _call_tistory_post_api(
            sb, blog_name, title, html_body, tags, thumbnail_url,
            category_id, entry_id=post.entry_id,
        )
        if not api_result:
            return PublishResult.fail("API 수정 실패")

        published_url, entry_id = api_result
        logger.info(f"API 수정 완료: {post.keyword} → {published_url} (id={entry_id})")

        # 공개 상태 검증
        http_code = _verify_published_url(published_url)
        if http_code == 200:
            logger.info(f"공개 검증 성공 (200): {published_url}")
            return PublishResult.ok(published_url, entry_id=entry_id)

        if http_code in (403, 404):
            logger.warning(f"수정 URL 비공개 감지 ({http_code}): {published_url}")
            fixed = _fix_post_visibility(sb, blog_name, published_url)
            if fixed:
                recheck = _verify_published_url(published_url)
                if recheck == 200:
                    return PublishResult.ok(published_url, entry_id=entry_id)
            return PublishResult.ok(published_url, entry_id=entry_id)

        logger.warning(f"수정 URL 검증 코드 {http_code}: {published_url}")
        return PublishResult.ok(published_url, entry_id=entry_id)

    except Exception as e:
        logger.error(f"수정 실패: {post.keyword} — {e}")
        return PublishResult.fail(str(e))


def _publish_via_api(
    sb, blog_name: str, content, html_body: str, post: Post,
) -> tuple[str, str] | None:
    """직접 API 호출로 포스트 발행 (React UI 버튼 클릭 대신).

    Tistory 에디터 내부 API: POST {manageUrl}/post.json
    성공 시 (발행 URL, entry_id) 튜플 반환, 실패 시 None.
    """
    title = content.title_or_fallback(post.keyword)
    tags = ",".join(content.tag_list()) if content.tags else ""
    thumbnail_url = content.thumbnail_url if content.thumbnail_url else ""
    if not thumbnail_url:
        thumbnail_url = _extract_first_image_url(html_body)
        if thumbnail_url:
            logger.info(f"대표이미지 자동 선택: {thumbnail_url[:80]}")
    category_id = _resolve_category_id(post.category)
    logger.info(f"카테고리 해석: '{post.category}' → ID {category_id}")

    # 방법 1: 직접 XHR API 호출 (visibility=20 명시적 전송, 가장 신뢰도 높음)
    api_result = _call_tistory_post_api(
        sb, blog_name, title, html_body, tags, thumbnail_url, category_id,
    )
    if api_result:
        return api_result

    # 방법 2: React 내부 상태를 통한 발행 (API 실패 시 fallback)
    react_url = _try_publish_via_react_state(
        sb, title, html_body, tags, blog_name, category_id,
    )
    if react_url:
        return (react_url, "")

    return None


def _call_tistory_post_api(
    sb, blog_name: str, title: str, html_body: str, tags: str,
    thumbnail_url: str = "", category_id: str = "0",
    content_type: str = "", entry_id: str = "0",
) -> tuple[str, str] | None:
    """POST /manage/post.json API 호출. 성공 시 (entryUrl, entryId) 반환.

    entry_id='0'이면 신규 생성, entry_id=<postId>이면 기존 글 수정.
    """
    import json as json_mod

    try:
        result_json = sb.driver.execute_async_script("""
            var callback = arguments[arguments.length - 1];
            var title = arguments[0];
            var content = arguments[1];
            var tags = arguments[2];
            var blogName = arguments[3];
            var thumbnailUrl = arguments[4] || '';
            var categoryId = arguments[5] || '0';
            var contentType = arguments[6] || '';
            var entryId = arguments[7] || '0';

            var manageUrl = '';
            if (window.appInfo && window.appInfo.manageUrl) {
                manageUrl = window.appInfo.manageUrl;
            } else {
                manageUrl = 'https://' + blogName + '.tistory.com/manage';
            }

            // Config 기본값
            var cfg = window.Config || {};
            var blogCfg = cfg.blog || {};
            var blogSettings = blogCfg.blogSettings || {};

            var catNum = parseInt(categoryId, 10) || 0;
            var postData = {
                id: entryId,
                title: title,
                content: content,
                slogan: '',
                visibility: '20',
                category: catNum,
                categoryId: catNum,
                tag: tags,
                acceptComment: '1',
                published: '1',
                password: Math.random().toString(36).substring(2, 10),
                uselessMarginForEntry: blogSettings.uselessMargin || '0',
                daumLike: '',
                cclCommercial: blogCfg.cclCommercial || '1',
                cclDerive: blogCfg.cclDerive || '1',
                thumbnail: thumbnailUrl,
                type: contentType || (cfg.postType || 'post'),
                attachments: '[]',
                recaptchaValue: '',
                draftSequence: null
            };

            var url = manageUrl + '/post.json';

            fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(postData),
                credentials: 'include'
            })
            .then(function(resp) {
                return resp.text().then(function(text) {
                    return { status: resp.status, text: text };
                });
            })
            .then(function(r) {
                var result = {
                    status: r.status,
                    response: r.text.substring(0, 2000),
                    url: url
                };

                if (r.status >= 200 && r.status < 300) {
                    try {
                        var data = JSON.parse(r.text);
                        result.success = true;
                        result.entryUrl = data.entryUrl || data.url || null;
                        result.entryId = data.entryId || data.id || null;
                    } catch(e) {
                        result.success = true;
                        result.parseError = e.message;
                    }
                } else {
                    result.success = false;
                }

                callback(JSON.stringify(result));
            })
            .catch(function(e) {
                callback(JSON.stringify({
                    success: false, error: 'fetch:' + e.message
                }));
            });
        """, title, html_body, tags, blog_name, thumbnail_url, category_id,
            content_type, entry_id)

        logger.info(f"API 발행 결과: {result_json}")

        if result_json:
            result = json_mod.loads(result_json)
            if result.get("success"):
                entry_url = result.get("entryUrl")
                entry_id = str(result.get("entryId") or result.get("id") or "")
                # entryId가 없으면 URL에서 추출 (/219 → 219)
                if not entry_id and entry_url:
                    url_parts = entry_url.rstrip("/").split("/")
                    if url_parts and url_parts[-1].isdigit():
                        entry_id = url_parts[-1]
                if entry_url:
                    return (entry_url, entry_id)
                if entry_id:
                    return (f"https://{blog_name}.tistory.com/{entry_id}", entry_id)
                resp_text = result.get("response", "")
                logger.warning(f"URL 미추출, response: {resp_text[:300]}")
                return (f"https://{blog_name}.tistory.com", "")
            else:
                resp_text = result.get("response", "")
                logger.error(
                    f"API 발행 실패 (status={result.get('status')}): "
                    f"{resp_text[:500]}"
                )
                if _DAILY_LIMIT_PATTERN in resp_text:
                    raise DailyPublishLimitError(resp_text[:200])
    except DailyPublishLimitError:
        raise
    except Exception as e:
        logger.error(f"API 발행 호출 예외: {e}")

    return None


def _try_publish_via_react_state(
    sb, title: str, html_body: str, tags: str, blog_name: str,
    category_id: str = "0",
) -> str | None:
    """React Redux store에 직접 접근하여 발행 액션을 디스패치.

    post-editor.min.js의 내부 store에 title/content/tags를 설정한 후
    publish 액션을 트리거한다. 성공 시 URL 반환.
    """
    try:
        result = sb.execute_script("""
            var title = arguments[0];
            var htmlContent = arguments[1];
            var tags = arguments[2];

            // 방법 A: React fiber를 통한 publish 버튼 onClick 트리거
            var btn = document.querySelector('#publish-layer-btn');
            if (!btn) return JSON.stringify({error: 'no-publish-btn'});

            // React 18+ __reactProps$ 또는 __reactFiber$ 키 탐색
            var keys = Object.keys(btn);
            var propsKey = keys.find(function(k) {
                return k.startsWith('__reactProps$');
            });
            var fiberKey = keys.find(function(k) {
                return k.startsWith('__reactFiber$')
                    || k.startsWith('__reactInternalInstance$');
            });

            // 먼저 title/content를 React state에 동기화
            // TinyMCE 에디터에 content가 이미 있으므로 title만 동기화
            var titleInput = document.querySelector('#post-title-inp');
            if (titleInput) {
                // React nativeInputValueSetter로 title 동기화
                var nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLTextAreaElement.prototype, 'value'
                );
                if (!nativeSetter) {
                    nativeSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    );
                }
                if (nativeSetter && nativeSetter.set) {
                    nativeSetter.set.call(titleInput, title);
                    titleInput.dispatchEvent(
                        new Event('input', {bubbles: true})
                    );
                    titleInput.dispatchEvent(
                        new Event('change', {bubbles: true})
                    );
                }
            }

            // __reactProps$ → onClick 직접 호출
            if (propsKey && btn[propsKey] && btn[propsKey].onClick) {
                btn[propsKey].onClick(
                    new MouseEvent('click', {bubbles: true})
                );
                return JSON.stringify({triggered: 'props-onClick'});
            }

            // __reactFiber$ → 트리 탐색하여 onClick 찾기
            if (fiberKey) {
                var fiber = btn[fiberKey];
                var depth = 0;
                while (fiber && depth < 30) {
                    var props = fiber.memoizedProps || fiber.pendingProps;
                    if (props && props.onClick) {
                        props.onClick(
                            new MouseEvent('click', {bubbles: true})
                        );
                        return JSON.stringify({
                            triggered: 'fiber-onClick',
                            depth: depth
                        });
                    }
                    fiber = fiber.return;
                    depth++;
                }
                return JSON.stringify({
                    error: 'fiber-no-handler', depth: depth
                });
            }

            return JSON.stringify({
                error: 'no-react-key',
                keys: keys.filter(function(k) {
                    return k.startsWith('__');
                }).join(',')
            });
        """, title, html_body, tags)

        logger.info(f"React 발행 트리거 결과: {result}")

        if not result:
            return None

        import json as json_mod
        data = json_mod.loads(result)

        if data.get("triggered"):
            # React onClick이 트리거됨 → 발행 레이어가 열렸는지 확인
            time.sleep(2)
            layer_info = _check_publish_layer_opened(sb)
            if layer_info:
                logger.info(f"발행 레이어 열림: {layer_info}")
                # 공개 모드 선택
                _select_public_mode(sb)
                # 카테고리 선택
                if category_id and category_id != "0":
                    _select_category_in_layer(sb, category_id)
                time.sleep(1)
                # 발행 확인 버튼 클릭
                return _click_publish_confirm_in_modal(sb, blog_name)
            else:
                logger.warning("React onClick 트리거 성공이나 레이어 미열림")

    except Exception as e:
        err_msg = str(e)
        if _DAILY_LIMIT_PATTERN in err_msg:
            logger.error("일일 발행 제한 도달 — 배치 중단")
            raise DailyPublishLimitError(
                "하루에 새롭게 공개 발행할 수 있는 글은 최대 15개까지입니다."
            ) from e
        logger.warning(f"React 발행 트리거 예외: {e}")

    return None


def _select_category_in_layer(sb, category_id: str) -> None:
    """발행 레이어에서 카테고리 select 요소의 값을 설정."""
    try:
        sb.execute_script("""
            var categoryId = arguments[0];
            // 카테고리 select 요소 탐색 (Tistory 에디터의 카테고리 드롭다운)
            var sel = document.querySelector(
                'select[name="category"], #category-btn, .publish-setting select'
            );
            if (sel && sel.tagName === 'SELECT') {
                sel.value = categoryId;
                sel.dispatchEvent(new Event('change', {bubbles: true}));
                return true;
            }
            // React state 직접 변경 fallback
            var inputs = document.querySelectorAll('select');
            for (var i = 0; i < inputs.length; i++) {
                var opts = inputs[i].options;
                for (var j = 0; j < opts.length; j++) {
                    if (opts[j].value === categoryId) {
                        inputs[i].value = categoryId;
                        inputs[i].dispatchEvent(
                            new Event('change', {bubbles: true})
                        );
                        return true;
                    }
                }
            }
            return false;
        """, category_id)
        logger.debug(f"카테고리 선택: {category_id}")
    except Exception as e:
        logger.warning(f"카테고리 선택 실패 (무시): {e}")


def _click_publish_confirm_in_modal(sb, blog_name: str) -> str | None:
    """발행 설정 모달에서 발행 확인 버튼 클릭. 성공 시 entryUrl 반환."""

    def _after_publish(sb, blog_name: str) -> str | None:
        """발행 후 실제 글 URL 추출."""
        time.sleep(5)
        current_url = sb.get_current_url()
        if "/manage/newpost" in current_url:
            return None  # 아직 에디터 → 실패
        # /manage/posts/ 리다이렉트 → 가장 최근 글 URL 추출
        if "/manage/" in current_url:
            extracted = _extract_published_url(sb, blog_name)
            if extracted:
                return extracted
            # fallback: /manage/posts 페이지에서 최신 글 링크 추출
            try:
                url = sb.execute_script("""
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
        _safe_click(sb, confirm_sel)
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


def _switch_to_markdown_mode(sb) -> None:
    """기본모드 → 마크다운 모드 전환 (확인 팝업 처리 포함)."""
    try:
        # 모드 전환 드롭다운 열기
        mode_btn = find_element(sb, MODE_SWITCH_BUTTON_SELECTORS, timeout=5)
        if not mode_btn:
            logger.warning("모드 전환 버튼 없음 — 기본모드로 진행")
            return

        sb.click(mode_btn)
        time.sleep(1)

        # 마크다운 옵션 선택
        md_sel = find_element(sb, MARKDOWN_MODE_SELECTORS, timeout=3)
        if md_sel:
            sb.click(md_sel)
            time.sleep(1)

            # 확인 팝업 처리 (1): 네이티브 alert
            try:
                sb.accept_alert(timeout=2)
                logger.info("마크다운 전환 alert 확인 완료")
            except Exception:
                pass  # alert 없으면 무시

            # 확인 팝업 처리: "작성 모드를 변경하시겠습니까?" 다이얼로그
            # 방법 1: CSS 셀렉터로 시도
            confirm_btn = find_element(sb, MODE_CONFIRM_SELECTORS, timeout=3)
            if confirm_btn:
                sb.click(confirm_btn)
                logger.info(f"마크다운 전환 확인 팝업 클릭: {confirm_btn}")
                time.sleep(2)
            else:
                # 방법 2: 페이지 전체에서 "확인" 텍스트를 가진 모든 버튼/링크 탐색
                clicked = sb.execute_script("""
                    // 모든 button, a, span, div 요소에서 "확인" 텍스트 찾기
                    var sel = 'button, a, span, div, input[type="button"]';
                    var allElements = document.querySelectorAll(sel);
                    for (var i = 0; i < allElements.length; i++) {
                        var el = allElements[i];
                        var txt = el.textContent.trim();
                        // 직계 텍스트만 확인 (자식 요소 텍스트 제외)
                        var directText = '';
                        for (var j = 0; j < el.childNodes.length; j++) {
                            if (el.childNodes[j].nodeType === 3) {
                                directText += el.childNodes[j].textContent.trim();
                            }
                        }
                        var checkText = directText || txt;
                        if (checkText === '확인' || checkText === 'OK') {
                            var rect = el.getBoundingClientRect();
                            var style = window.getComputedStyle(el);
                            // 화면에 보이고 크기가 있는 요소만
                            if (rect.width > 0 && rect.height > 0
                                && style.display !== 'none'
                                && style.visibility !== 'hidden') {
                                el.click();
                                return 'clicked: ' + el.tagName +
                                    '.' + el.className +
                                    ' (' + checkText + ')';
                            }
                        }
                    }
                    return null;
                """)
                if clicked:
                    logger.info(f"JS로 확인 버튼 클릭 성공: {clicked}")
                    time.sleep(2)
                else:
                    logger.warning("확인 버튼을 찾지 못함")
                    # 디버깅: 현재 화면의 보이는 요소 중 "확인" 포함 항목 로깅
                    debug_info = sb.execute_script("""
                        var result = [];
                        var all = document.querySelectorAll('*');
                        for (var i = 0; i < all.length; i++) {
                            var el = all[i];
                            var txt = el.textContent.trim();
                            if (txt.includes('확인') || txt.includes('취소')
                                || txt.includes('변경')) {
                                var rect = el.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {
                                    result.push(el.tagName + '.' + el.className +
                                        ' [' + txt.substring(0, 50) + '] rect:' +
                                        Math.round(rect.x) + ',' + Math.round(rect.y));
                                }
                            }
                            if (result.length > 15) break;
                        }
                        return result.join('\\n');
                    """)
                    if debug_info:
                        logger.info(f"'확인' 포함 요소:\n{debug_info}")
                    time.sleep(1)

            # CodeMirror가 실제로 로드되었는지 확인
            cm_ready = find_element(sb, [".CodeMirror"], timeout=5)
            if cm_ready:
                logger.info("마크다운 모드 전환 완료 — CodeMirror 확인됨")
            else:
                logger.warning("마크다운 전환 후 CodeMirror 미발견")
        else:
            logger.warning("마크다운 옵션 없음 — 기본모드로 진행")

    except Exception as e:
        logger.warning(f"모드 전환 중 오류 (무시): {e}")


def _inject_markdown_content(sb, markdown_text: str) -> bool:
    """마크다운 모드의 CodeMirror에 본문 주입."""
    # 방법 1: CodeMirror API — setValue + save + 이벤트 트리거
    try:
        content_sel = find_element(sb, CONTENT_AREA_SELECTORS, timeout=5)
        if content_sel and "CodeMirror" in content_sel:
            result = sb.execute_script("""
                var cm = document.querySelector('.CodeMirror');
                if (cm && cm.CodeMirror) {
                    var editor = cm.CodeMirror;
                    var text = arguments[0];
                    editor.focus();
                    editor.setValue(text);
                    editor.save();
                    editor.refresh();
                    // 1. underlying textarea 직접 동기화
                    try {
                        var ta = editor.getTextArea();
                        if (ta) {
                            ta.value = text;
                            ta.dispatchEvent(
                                new Event('input', {bubbles: true})
                            );
                            ta.dispatchEvent(
                                new Event('change', {bubbles: true})
                            );
                        }
                    } catch(e) {}
                    // 2. #editor-tistory textarea 동기화 (핵심!)
                    var edTa = document.getElementById('editor-tistory');
                    if (edTa) {
                        edTa.value = text;
                        edTa.dispatchEvent(
                            new Event('input', {bubbles: true})
                        );
                        edTa.dispatchEvent(
                            new Event('change', {bubbles: true})
                        );
                    }
                    // 3. content 관련 hidden 폼 필드 동기화
                    var sel = [
                        'textarea[name*="content"]',
                        'input[name*="content"]',
                        'textarea[name*="body"]',
                        'input[name*="body"]'
                    ].join(',');
                    var fields = document.querySelectorAll(sel);
                    for (var i = 0; i < fields.length; i++) {
                        fields[i].value = text;
                        fields[i].dispatchEvent(
                            new Event('change', {bubbles: true})
                        );
                    }
                    // 3. CodeMirror 내부 change signal 트리거
                    try {
                        CodeMirror.signal(editor, 'changes',
                            editor, [{
                                from: {line:0, ch:0},
                                to: {line:0, ch:0},
                                text: text.split('\\n'),
                                removed: [''],
                                origin: '+input'
                            }]
                        );
                    } catch(e) {}
                    // 4. DOM 이벤트
                    cm.dispatchEvent(
                        new Event('input', {bubbles: true})
                    );
                    cm.dispatchEvent(
                        new Event('change', {bubbles: true})
                    );
                    return editor.getValue().length;
                }
                return 0;
            """, markdown_text)
            if result and result > 0:
                logger.info(f"CodeMirror API로 본문 주입 성공 ({result}자)")
                return True
            else:
                logger.warning("CodeMirror setValue 실행했으나 내용 없음")
    except Exception as e:
        logger.debug(f"CodeMirror 주입 실패: {e}")

    # 방법 2: CodeMirror에 클립보드로 붙여넣기
    try:
        content_sel = find_element(sb, CONTENT_AREA_SELECTORS, timeout=3)
        if content_sel and "CodeMirror" in content_sel:
            # CodeMirror 에디터 영역 클릭 후 전체 선택 → 붙여넣기
            sb.click(content_sel + " .CodeMirror-lines")
            time.sleep(0.5)
            # JavaScript로 클립보드에 텍스트 복사 후 붙여넣기 이벤트 발생
            sb.execute_script("""
                var cm = document.querySelector('.CodeMirror').CodeMirror;
                cm.focus();
                cm.execCommand('selectAll');
                cm.replaceSelection(arguments[0]);
                cm.save();
            """, markdown_text)
            time.sleep(1)
            verify_len = sb.execute_script("""
                var cm = document.querySelector('.CodeMirror');
                return cm && cm.CodeMirror ? cm.CodeMirror.getValue().length : 0;
            """)
            if verify_len and verify_len > 0:
                logger.info(f"CodeMirror replaceSelection으로 본문 주입 성공 ({verify_len}자)")
                return True
    except Exception as e:
        logger.debug(f"CodeMirror replaceSelection 실패: {e}")

    # 방법 3: TinyMCE API로 HTML 주입 (기본모드 fallback)
    try:
        success = sb.execute_script("""
            if (typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor) {
                var html = '<pre>' + arguments[0].replace(/</g, '&lt;') + '</pre>';
                tinyMCE.activeEditor.setContent(html);
                return true;
            }
            return false;
        """, markdown_text)
        if success:
            logger.info("TinyMCE API로 본문 주입 성공 (fallback)")
            return True
    except Exception as e:
        logger.debug(f"TinyMCE 주입 실패: {e}")

    # 방법 4: textarea 직접 입력 (최후 수단)
    try:
        content_sel = find_element(sb, CONTENT_AREA_SELECTORS, timeout=3)
        if content_sel:
            sb.click(content_sel)
            sb.type(content_sel, markdown_text)
            logger.info("직접 타이핑으로 본문 입력 (fallback)")
            return True
    except Exception as e:
        logger.debug(f"직접 타이핑 실패: {e}")

    return False


def _render_mermaid_via_kroki(code: str) -> str | None:
    """kroki.io API로 Mermaid 코드를 SVG로 렌더링.

    POST https://kroki.io/mermaid/svg 에 plaintext body를 전송하여 SVG를 반환받는다.
    실패 시 None을 반환한다 (graceful degradation).
    """
    import urllib.request

    try:
        req = urllib.request.Request(
            "https://kroki.io/mermaid/svg",
            data=code.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            svg = resp.read().decode("utf-8")
        if "<svg" in svg:
            return svg
        return None
    except Exception:
        return None


def _preserve_mermaid_blocks(md_text: str) -> str:
    """잔류 Mermaid 코드블록을 SVG 또는 styled HTML로 사전 변환.

    1차: kroki.io API로 SVG 렌더링 시도
    2차 (실패 시): styled fallback <div>로 변환
    codehilite extension이 ```mermaid 블록을 구문 강조 처리하여
    language-mermaid 클래스가 사라지는 것을 방지한다.
    Markdown은 raw HTML을 그대로 통과시키므로, 사전에 HTML로 변환한다.
    """
    import html as html_lib

    def _replace(match: re.Match) -> str:
        code = match.group(1).strip()
        first_line = code.split("\n")[0].strip()
        alt_text = f"Mermaid diagram: {first_line}"
        safe_alt = alt_text.replace('"', "&quot;")

        # 1차: kroki.io SVG 렌더링 시도
        svg = _render_mermaid_via_kroki(code)
        if svg:
            # SVG에 width가 없으면 반응형 설정
            processed_svg = svg
            if "width=" not in processed_svg:
                processed_svg = processed_svg.replace("<svg", '<svg width="100%"', 1)
            return (
                f'<div class="mermaid-diagram" role="img" aria-label="{safe_alt}" '
                f'style="max-width:100%;overflow-x:auto;margin:16px 0;">'
                f"{processed_svg}</div>"
            )

        # 2차: fallback — styled code block
        escaped_code = html_lib.escape(code)
        return (
            '<div class="mermaid-fallback" style="background:#f0f4f8;border:1px solid #d0d7de;'
            'border-radius:6px;padding:8px;margin:16px 0;overflow-x:auto;">'
            f'<pre><code class="language-mermaid">{escaped_code}</code></pre></div>'
        )

    # 1) [MERMAID]...[/MERMAID] 커스텀 마커 (Pipeline A에서 inject_images.js 실패 시 잔류)
    result = re.sub(r"\[MERMAID\]([\s\S]*?)\[/MERMAID\]", _replace, md_text)
    # 2) ```mermaid...``` 코드블록 (하위호환)
    return re.sub(r"```mermaid\n([\s\S]*?)```", _replace, result)


def convert_markdown_to_html(md_text: str) -> str:
    """마크다운 텍스트를 HTML로 변환.

    Extensions: tables, fenced_code, nl2br, sane_lists, codehilite, toc
    - codehilite: noclasses=True → 인라인 스타일 (외부 CSS 불필요)
    - toc: H2~H3 목차 자동 생성, 첫 번째 <h2> 앞에 삽입
    - 잔류 Mermaid 블록: codehilite 처리 전에 styled HTML로 사전 변환
    """
    if not md_text or not md_text.strip():
        return ""

    # Mermaid 코드블록 사전 처리 (codehilite보다 먼저 실행)
    md_text = _preserve_mermaid_blocks(md_text)

    extensions = ["tables", "fenced_code", "nl2br", "sane_lists", "codehilite", "toc"]
    extension_configs = {
        "codehilite": {"css_class": "highlight", "linenums": False, "noclasses": True},
        "toc": {"permalink": False, "toc_depth": "2-3"},
    }
    md = md_lib.Markdown(extensions=extensions, extension_configs=extension_configs)
    html_body: str = md.convert(md_text)

    # TOC 자동 삽입: 첫 번째 <h2> 앞에 목차 배치
    toc_html = getattr(md, "toc", "")
    if toc_html and "<li>" in toc_html:
        toc_block = f'<div class="toc-container"><h2>목차</h2>{toc_html}</div>\n\n'
        h2_pos = html_body.find("<h2")
        if h2_pos >= 0:
            html_body = html_body[:h2_pos] + toc_block + html_body[h2_pos:]

    # Mermaid fallback 스타일링 (렌더링 실패한 잔류 코드블록에 시각적 힌트)
    html_body = _style_mermaid_fallback(html_body)

    return html_body


def _style_mermaid_fallback(html_text: str) -> str:
    """렌더링 실패한 Mermaid 코드블록에 시각적 힌트 추가.

    <pre><code class="language-mermaid">...  →
    <div class="mermaid-fallback" style="..."><pre><code>...
    """
    if 'language-mermaid' not in html_text:
        return html_text

    return re.sub(
        r'(<pre[^>]*><code[^>]*class="[^"]*language-mermaid[^"]*"[^>]*>)',
        r'<div class="mermaid-fallback" style="background:#f0f4f8;border:1px solid #d0d7de;'
        r'border-radius:6px;padding:8px;margin:16px 0;overflow-x:auto;">\1',
        html_text,
    ).replace('</code></pre>', '</code></pre></div>')


def _add_lazy_loading(html_text: str) -> str:
    """<img> 태그에 loading="lazy" 속성을 추가. 첫 번째 이미지는 제외 (LCP candidate)."""
    if not html_text:
        return html_text
    count = 0

    def _replace_img(match: re.Match) -> str:
        nonlocal count
        count += 1
        if count == 1:
            # 첫 번째 이미지: LCP candidate이므로 lazy loading 미적용
            return match.group(0)
        return '<img loading="lazy" ' + match.group(0)[5:]

    return re.sub(r"<img\s(?!.*loading=)", _replace_img, html_text)


def _add_nofollow_to_external_links(html_text: str, blog_name: str) -> str:
    """외부 링크 <a> 태그에 rel="nofollow noopener" target="_blank" 추가.

    내부 링크 (같은 블로그 도메인)는 제외.
    """
    if not html_text:
        return html_text

    internal_pattern = re.compile(
        rf'https?://({re.escape(blog_name)}\.tistory\.com|tistory\.com)',
        re.IGNORECASE,
    )

    def _process_anchor(match: re.Match) -> str:
        tag = match.group(0)
        href_match = re.search(r'href="([^"]*)"', tag)
        if not href_match:
            return tag
        href = href_match.group(1)
        # 내부 링크, 앵커, 빈 href는 건드리지 않음
        if not href or href.startswith('#') or internal_pattern.search(href):
            return tag
        # 이미 rel이 있으면 건드리지 않음
        if 'rel=' in tag:
            return tag
        # target="_blank"과 rel 추가
        tag = tag.rstrip('>')
        if 'target=' not in tag:
            tag += ' target="_blank"'
        tag += ' rel="nofollow noopener">'
        return tag

    return re.sub(r'<a\s[^>]*>', _process_anchor, html_text)


def validate_html(html_text: str) -> bool:
    """HTML 변환 결과를 검증.

    검증 항목:
      1. <h2> 또는 <h3> 태그 존재
      2. <p> 태그 존재
      3. 마크다운 잔여 문법 미포함 (## , **, |---|)
      4. 본문 길이 >= 1,500자 (태그 제거 후 순수 텍스트)
      5. <!-- IMAGE: --> 마커 잔류 → hard fail
      6. <img> 태그 0개 → warning only
    """
    if not html_text:
        logger.warning("HTML 검증 실패: 빈 콘텐츠")
        return False

    ok = True

    # 1. 헤딩 태그 확인
    if not re.search(r"<h[23][^>]*>", html_text):
        logger.warning("HTML 검증: <h2>/<h3> 태그 없음")
        ok = False

    # 2. 단락 태그 확인
    if "<p>" not in html_text:
        logger.warning("HTML 검증: <p> 태그 없음")
        ok = False

    # 3. 마크다운 잔여 문법 확인 (코드 블록 밖에서만)
    # <pre>/<code> 블록 제거 후 검사
    stripped = re.sub(r"<pre[^>]*>.*?</pre>", "", html_text, flags=re.DOTALL)
    stripped = re.sub(r"<code[^>]*>.*?</code>", "", stripped, flags=re.DOTALL)

    residual_patterns = [
        (r"(?m)^#{1,6}\s", "마크다운 헤딩(## )"),
        (r"\*\*[^*]+\*\*", "볼드(**text**)"),
        (r"\|---", "테이블 구분선(|---)"),
    ]
    for pattern, desc in residual_patterns:
        if re.search(pattern, stripped):
            logger.warning(f"HTML 검증: 잔여 마크다운 문법 — {desc}")
            ok = False

    # 4. 본문 길이 검증 (태그 제거 후 순수 텍스트)
    plain_text = re.sub(r"<[^>]+>", "", html_text)
    plain_text = plain_text.strip()
    if len(plain_text) < 1500:
        logger.warning(f"HTML 검증: 본문 길이 부족 ({len(plain_text)}자, 최소 1,500자)")
        ok = False

    # 5. IMAGE 마커 잔류 → hard fail
    if re.search(r"<!-- IMAGE:\s*.+?\s*-->", html_text):
        logger.warning("HTML 검증: IMAGE 마커 잔류 — 이미지 삽입 미처리")
        ok = False

    # 6. <img> 태그 0개 → warning only (ok 플래그 미변경)
    if not re.search(r"<img\s", html_text):
        logger.warning("HTML 검증 경고: <img> 태그 없음 (이미지 0개)")

    # 7. Mermaid 코드블록 잔류 → warning only (ok 플래그 미변경)
    if re.search(r'class="[^"]*language-mermaid', html_text):
        logger.warning("HTML 검증 경고: Mermaid 코드블록 미렌더링 잔류")

    # 8. FAQ LD+JSON 스키마 존재 여부 (info only — 주입 전 호출이므로 통과)
    if '<script type="application/ld+json">' not in html_text:
        logger.info("validate_html: FAQ LD+JSON 스키마 미포함 (faq_schema 없는 글)")

    return ok


def _wait_for_wysiwyg_editor(sb, timeout: int = 10) -> None:
    """WYSIWYG 에디터(TinyMCE/iframe)가 로드될 때까지 대기."""
    try:
        # TinyMCE iframe 또는 에디터 존재 확인
        iframe_sel = find_element(sb, TINYMCE_IFRAME_SELECTORS, timeout=timeout)
        if iframe_sel:
            logger.info("WYSIWYG 에디터 로드 완료 (TinyMCE iframe)")
            return

        # TinyMCE API 로드 확인
        for _ in range(timeout):
            ready = sb.execute_script(
                "return typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor != null;"
            )
            if ready:
                logger.info("WYSIWYG 에디터 로드 완료 (TinyMCE API)")
                return
            time.sleep(1)

        logger.warning("WYSIWYG 에디터 로드 타임아웃 — 그대로 진행")
    except Exception as e:
        logger.warning(f"WYSIWYG 에디터 대기 중 오류: {e}")


def _inject_html_content(sb, html_text: str) -> bool:
    """WYSIWYG 모드의 에디터에 HTML 본문 주입."""
    # 방법 1: TinyMCE API — setContent + save
    try:
        result = sb.execute_script("""
            var html = arguments[0];
            if (typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor) {
                var ed = tinyMCE.activeEditor;
                ed.setContent(html);
                ed.save();
                // #editor-tistory textarea 동기화
                var ta = document.getElementById('editor-tistory');
                if (ta) {
                    ta.value = html;
                    ta.dispatchEvent(new Event('input', {bubbles: true}));
                    ta.dispatchEvent(new Event('change', {bubbles: true}));
                }
                return ed.getContent().length;
            }
            return 0;
        """, html_text)
        if result and result > 0:
            logger.info(f"TinyMCE API로 HTML 본문 주입 성공 ({result}자)")
            return True
    except Exception as e:
        logger.debug(f"TinyMCE 주입 실패: {e}")

    # 방법 2: iframe body innerHTML 직접 설정
    try:
        result = sb.execute_script("""
            var html = arguments[0];
            var iframe = document.querySelector('#editor-tistory_ifr');
            if (iframe && iframe.contentDocument && iframe.contentDocument.body) {
                iframe.contentDocument.body.innerHTML = html;
                // #editor-tistory textarea 동기화
                var ta = document.getElementById('editor-tistory');
                if (ta) {
                    ta.value = html;
                    ta.dispatchEvent(new Event('input', {bubbles: true}));
                    ta.dispatchEvent(new Event('change', {bubbles: true}));
                }
                return iframe.contentDocument.body.innerHTML.length;
            }
            return 0;
        """, html_text)
        if result and result > 0:
            logger.info(f"iframe innerHTML로 HTML 주입 성공 ({result}자)")
            return True
    except Exception as e:
        logger.debug(f"iframe 주입 실패: {e}")

    # 방법 3: #editor-tistory textarea 직접 설정 + content 관련 hidden 필드
    try:
        result = sb.execute_script("""
            var html = arguments[0];
            var ta = document.getElementById('editor-tistory');
            if (ta) {
                ta.value = html;
                ta.dispatchEvent(new Event('input', {bubbles: true}));
                ta.dispatchEvent(new Event('change', {bubbles: true}));
            }
            // content/body 관련 hidden 필드 동기화
            var sel = [
                'textarea[name*="content"]', 'input[name*="content"]',
                'textarea[name*="body"]', 'input[name*="body"]'
            ].join(',');
            var fields = document.querySelectorAll(sel);
            for (var i = 0; i < fields.length; i++) {
                fields[i].value = html;
                fields[i].dispatchEvent(new Event('change', {bubbles: true}));
            }
            return ta ? ta.value.length : 0;
        """, html_text)
        if result and result > 0:
            logger.info(f"textarea 직접 설정으로 HTML 주입 ({result}자)")
            return True
    except Exception as e:
        logger.debug(f"textarea 주입 실패: {e}")

    # 방법 4: CodeMirror fallback (마크다운 모드인 경우)
    try:
        result = sb.execute_script("""
            var html = arguments[0];
            var cm = document.querySelector('.CodeMirror');
            if (cm && cm.CodeMirror) {
                cm.CodeMirror.setValue(html);
                cm.CodeMirror.save();
                return cm.CodeMirror.getValue().length;
            }
            return 0;
        """, html_text)
        if result and result > 0:
            logger.info(f"CodeMirror fallback으로 HTML 주입 ({result}자)")
            return True
    except Exception as e:
        logger.debug(f"CodeMirror fallback 실패: {e}")

    logger.error("모든 HTML 주입 방법 실패")
    return False


def _select_public_mode(sb) -> None:
    """발행 설정 레이어에서 공개 모드를 선택.

    React SPA이므로 DOM 클릭만으로는 React state가 갱신되지 않는다.
    React fiber의 onChange 핸들러를 직접 호출하여 state를 동기화한다.
    """
    try:
        result = sb.execute_script("""
            // 공개 라디오 버튼 찾기 (value='0')
            var radios = document.querySelectorAll(
                'input[name="visibility"], input[name="openType"], '
                + 'input[type="radio"]'
            );
            var publicRadio = null;
            for (var i = 0; i < radios.length; i++) {
                if (radios[i].value === '0') {
                    publicRadio = radios[i];
                    break;
                }
            }
            if (!publicRadio) {
                // ID 기반 fallback
                publicRadio = document.querySelector('#open-type-0');
            }
            if (!publicRadio) return 'not-found';

            // 1단계: DOM 상태 변경
            publicRadio.checked = true;

            // 2단계: React fiber의 onChange 핸들러 직접 호출
            var keys = Object.keys(publicRadio);
            var propsKey = keys.find(function(k) {
                return k.startsWith('__reactProps$');
            });
            if (propsKey && publicRadio[propsKey]
                    && publicRadio[propsKey].onChange) {
                publicRadio[propsKey].onChange({
                    target: publicRadio,
                    currentTarget: publicRadio,
                    type: 'change',
                    preventDefault: function() {},
                    stopPropagation: function() {}
                });
                return 'react-onChange:' + publicRadio.id;
            }

            // 3단계: fiber 트리 탐색으로 onChange 찾기
            var fiberKey = keys.find(function(k) {
                return k.startsWith('__reactFiber$')
                    || k.startsWith('__reactInternalInstance$');
            });
            if (fiberKey) {
                var fiber = publicRadio[fiberKey];
                var depth = 0;
                while (fiber && depth < 15) {
                    var props = fiber.memoizedProps || fiber.pendingProps;
                    if (props && props.onChange) {
                        props.onChange({
                            target: publicRadio,
                            currentTarget: publicRadio,
                            type: 'change',
                            preventDefault: function() {},
                            stopPropagation: function() {}
                        });
                        return 'fiber-onChange:depth=' + depth;
                    }
                    fiber = fiber.return;
                    depth++;
                }
            }

            // 4단계: native event fallback
            publicRadio.click();
            publicRadio.dispatchEvent(
                new Event('change', {bubbles: true})
            );
            publicRadio.dispatchEvent(
                new Event('input', {bubbles: true})
            );
            // label 클릭도 시도
            var label = document.querySelector(
                'label[for="' + publicRadio.id + '"]'
            );
            if (label) label.click();
            return 'native-event:' + publicRadio.id;
        """)
        if result and result != 'not-found':
            logger.info(f"공개 모드 선택: {result}")
        else:
            logger.warning("공개 옵션을 찾지 못함 — 기본 상태로 발행")
    except Exception as e:
        logger.warning(f"공개 모드 선택 중 오류 (무시): {e}")


def _extract_published_url(sb, blog_name: str) -> str | None:
    """발행 후 관리 페이지에서 방금 발행한 글의 실제 URL을 추출."""
    try:
        time.sleep(2)
        # 관리 페이지에서 해당 블로그의 첫 번째 글 링크 추출
        url = sb.execute_script("""
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


def _verify_published_url(url: str, timeout: int = 10) -> int:
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
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as exc:
        logger.debug(f"URL 검증 요청 실패: {exc}")
        return 0


def _extract_post_id(url: str) -> str | None:
    """티스토리 URL에서 게시글 ID 추출. e.g. '.../211' → '211'."""
    m = re.search(r"/(\d+)$", url)
    return m.group(1) if m else None


def _fix_post_visibility(sb, blog_name: str, published_url: str) -> bool:
    """비공개로 발행된 글을 공개(visibility=20)로 수정.

    Tistory 내부 API: POST /manage/post.json (id 포함 시 수정 동작).
    """
    import json as json_mod

    post_id = _extract_post_id(published_url)
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


def _input_tags(sb, tags: list[str]) -> None:
    """태그 입력 (개별 태그를 Enter 키로 등록)."""
    try:
        tag_sel = find_element(sb, TAG_INPUT_SELECTORS, timeout=5)
        if not tag_sel:
            logger.warning("태그 입력창을 찾을 수 없음")
            return

        for tag in tags:
            _safe_click(sb, tag_sel)
            time.sleep(0.3)
            # 태그 입력: 네이티브 시도 → JS fallback (Enter 키 이벤트 포함)
            try:
                sb.type(tag_sel, tag + "\n")
            except Exception:
                safe_tag = tag.replace("\\", "\\\\").replace("'", "\\'")
                sb.execute_script(
                    f"var el = document.querySelector('{tag_sel}');"
                    "if (!el) return;"
                    f"el.focus(); el.value = '{safe_tag}';"
                    "el.dispatchEvent(new Event('input', {bubbles: true}));"
                    "el.dispatchEvent(new KeyboardEvent('keydown',"
                    "  {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));"
                )
            time.sleep(0.5)

        # 등록된 태그 수 확인
        tag_count = sb.execute_script("""
            var container = document.querySelector('.editor_tag, .area_tag');
            if (!container) return 0;
            // 삭제(×) 버튼이 있는 span이 태그 아이템
            return container.querySelectorAll('button, .btn_delete, a.link_delete')
                .length;
        """)
        logger.info(f"태그 입력 완료: {tags} (등록된 태그: {tag_count}개)")
    except Exception as e:
        logger.warning(f"태그 입력 중 오류 (무시): {e}")


def _inject_meta_description(sb, meta_description: str) -> None:
    """발행 설정 레이어 또는 에디터의 meta description 필드에 값 주입."""
    try:
        result = sb.execute_script("""
            var desc = arguments[0];
            // 방법 1: 발행 설정의 description textarea/input
            var selectors = [
                '#post-description',
                'textarea[name="description"]',
                'input[name="description"]',
                '#meta-description',
                'textarea.tf_excerpt',
                '#excerpt'
            ];
            for (var i = 0; i < selectors.length; i++) {
                var el = document.querySelector(selectors[i]);
                if (el) {
                    el.value = desc;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    return 'injected:' + selectors[i];
                }
            }
            // 방법 2: og:description / name=description 메타 태그 직접 생성은
            // 발행 시 Tistory가 자체 처리하므로 여기서는 폼 필드만 처리
            return null;
        """, meta_description)
        if result:
            logger.info(f"메타 설명 주입: {result}")
        else:
            logger.warning("메타 설명 필드를 찾지 못함 — 건너뜀")
    except Exception as e:
        logger.warning(f"메타 설명 주입 중 오류 (무시): {e}")


def _install_ajax_content_interceptor(sb, markdown_text: str) -> None:
    """XHR/fetch 인터셉터를 설치하여 빈 content를 실제 본문으로 교체."""
    try:
        sb.execute_script("""
            var text = arguments[0];
            // XHR 인터셉트
            if (!window._contentInterceptorInstalled) {
                var origSend = XMLHttpRequest.prototype.send;
                XMLHttpRequest.prototype.send = function(body) {
                    if (body && typeof body === 'string') {
                        try {
                            var data = JSON.parse(body);
                            if ('content' in data && !data.content) {
                                data.content = window._pendingContent || '';
                                body = JSON.stringify(data);
                            }
                        } catch(e) {}
                    }
                    return origSend.call(this, body);
                };
                // Fetch 인터셉트
                var origFetch = window.fetch;
                window.fetch = function(url, options) {
                    if (options && options.body
                            && typeof options.body === 'string') {
                        try {
                            var data = JSON.parse(options.body);
                            if ('content' in data && !data.content) {
                                data.content =
                                    window._pendingContent || '';
                                options.body = JSON.stringify(data);
                            }
                        } catch(e) {}
                    }
                    return origFetch.apply(this, arguments);
                };
                window._contentInterceptorInstalled = true;
            }
            window._pendingContent = text;
        """, markdown_text)
        logger.info("AJAX content 인터셉터 설치 완료")
    except Exception as e:
        logger.warning(f"AJAX 인터셉터 설치 실패: {e}")


def _verify_faq_schema(url: str, timeout: int = 10) -> bool:
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


def _append_faq_schema(body_markdown: str, faq_ld_json: str) -> str:
    """본문 하단에 FAQ LD+JSON 스키마를 추가."""
    schema_block = (
        '\n\n<script type="application/ld+json">\n'
        f'{faq_ld_json}\n'
        '</script>'
    )
    return body_markdown + schema_block


def _ensure_content_in_form(sb, html_text: str) -> None:
    """저장/발행 직전 콘텐츠가 폼 필드에 동기화되었는지 확인 및 재동기화."""
    try:
        result = sb.execute_script("""
            var html = arguments[0];
            var info = [];
            // TinyMCE 동기화
            if (typeof tinyMCE !== 'undefined' && tinyMCE.activeEditor) {
                var ed = tinyMCE.activeEditor;
                var edLen = ed.getContent().length;
                if (edLen === 0) {
                    ed.setContent(html);
                    info.push('tinymce-reinjected');
                }
                ed.save();
                info.push('tinymce:' + ed.getContent().length);
            }
            // CodeMirror 동기화 (마크다운 모드 fallback)
            var cm = document.querySelector('.CodeMirror');
            if (cm && cm.CodeMirror) {
                var editor = cm.CodeMirror;
                var cmLen = editor.getValue().length;
                if (cmLen === 0) {
                    editor.setValue(html);
                    info.push('cm-reinjected');
                }
                editor.save();
                info.push('cm:' + editor.getValue().length);
            }
            // #editor-tistory textarea (티스토리 핵심 필드)
            var edTa = document.getElementById('editor-tistory');
            if (edTa) {
                if (edTa.value.length === 0 || edTa.value !== html) {
                    edTa.value = html;
                    edTa.dispatchEvent(
                        new Event('input', {bubbles: true})
                    );
                    edTa.dispatchEvent(
                        new Event('change', {bubbles: true})
                    );
                    info.push('ed-tistory-fixed:' + html.length);
                } else {
                    info.push('ed-tistory-ok:' + edTa.value.length);
                }
            }
            return info.join(', ');
        """, html_text)
        if result:
            logger.info(f"콘텐츠 동기화 상태: {result}")
    except Exception as e:
        logger.warning(f"콘텐츠 동기화 확인 중 오류: {e}")
