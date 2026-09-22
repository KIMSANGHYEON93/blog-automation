"""api_publisher — Tistory API (XHR) and React Redux state publishing."""
from __future__ import annotations

import logging
import time

from src.domain.exceptions import DailyPublishLimitError
from src.infrastructure.browser import form_filler, publish_verifier

logger = logging.getLogger(__name__)

_DAILY_LIMIT_PATTERN = "최대 15개까지"


def call_tistory_post_api(
    sb, blog_name: str, title: str, html_body: str, tags: str,
    thumbnail_url: str = "", category_id: str = "0",
    content_type: str = "", entry_id: str = "0",
    view_channel: str = "",
    *, max_retries: int = 3,
) -> tuple[str, str] | None:
    """Tistory 글 저장 API 호출. 성공 시 (entryUrl, entryId) 반환.

    entry_id='0'이면 신규 생성(POST /manage/post.json),
    그 외에는 기존 글 수정(PUT /manage/post/<id>.json).
    에디터 번들(post-editor.min.js)이 쓰는 분기와 동일하다 —
    수정인데 POST /post.json을 쓰면 서버가 새 글을 만든다.
    script timeout 시 window.__publishResult를 확인하여 중복 방지.
    """
    import contextlib

    for attempt in range(max_retries):
        if attempt > 0:
            backoff = 3 * (2 ** (attempt - 1))  # 3s, 6s, 12s
            timeout = 120 + 60 * attempt  # 180s, 240s
            logger.info(
                f"API 발행 재시도 ({attempt + 1}/{max_retries}), "
                f"backoff={backoff}s, timeout={timeout}s"
            )

            with contextlib.suppress(Exception):
                sb.driver.set_script_timeout(timeout)
            # backoff 대기 — 이 동안 timed-out fetch가 완료될 수 있음
            time.sleep(backoff)

            # backoff 후: script timeout된 fetch가 실제 성공했는지 확인
            saved = _check_saved_publish_result(sb, blog_name)
            if saved is not None:
                logger.info(
                    f"script timeout 후 fetch 성공 확인 — 재시도 불필요: {saved[0]}"
                )
                return saved

        result = _call_tistory_post_api_once(
            sb, blog_name, title, html_body, tags,
            thumbnail_url, category_id, content_type, entry_id,
            view_channel,
        )
        if result is not None:
            if not _is_expected_entry(result, entry_id):
                logger.error(
                    f"수정 요청({entry_id})인데 다른 글이 반환됨: {result[0]} — "
                    "중복 글 생성 가능성. 시트를 덮어쓰지 않고 실패 처리한다."
                )
                return None
            return result

    return None


def _is_expected_entry(result: tuple[str, str], entry_id: str) -> bool:
    """수정 호출의 응답이 요청한 글과 같은지 확인.

    Tistory는 잘못된 수정 요청을 오류 대신 '새 글 생성'으로 처리한다.
    이 검증이 없으면 시트 URL이 새 중복 글로 덮어써진다(2026-04, 2026-09 사고).
    """
    if not entry_id or entry_id == "0":
        return True
    returned_url, returned_id = result
    if returned_id:
        return returned_id == entry_id
    return returned_url.rstrip("/").endswith(f"/{entry_id}")


def _check_saved_publish_result(
    sb, blog_name: str,
) -> tuple[str, str] | None:
    """script timeout 후 window.__publishResult에 저장된 결과를 확인."""
    import contextlib
    import json as json_mod

    try:
        raw = sb.execute_script("return window.__publishResult || null;")
        if not raw:
            return None
        result = json_mod.loads(raw) if isinstance(raw, str) else raw
        if result.get("success"):
            entry_url = result.get("entryUrl", "")
            entry_id = str(result.get("entryId") or "")
            if not entry_id and entry_url:
                url_parts = entry_url.rstrip("/").split("/")
                if url_parts and url_parts[-1].isdigit():
                    entry_id = url_parts[-1]
            if entry_url:
                return (entry_url, entry_id)
            if entry_id:
                return (f"https://{blog_name}.tistory.com/{entry_id}", entry_id)
    except Exception:
        with contextlib.suppress(Exception):
            logger.debug("window.__publishResult 확인 실패")
    return None


def _call_tistory_post_api_once(
    sb, blog_name: str, title: str, html_body: str, tags: str,
    thumbnail_url: str = "", category_id: str = "0",
    content_type: str = "", entry_id: str = "0",
    view_channel: str = "",
) -> tuple[str, str] | None:
    """단일 API 호출 시도."""
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
            var viewChannel = arguments[8] || '';

            // 이전 결과 초기화 (script timeout 후 확인용)
            window.__publishResult = null;

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
                daumLike: viewChannel,
                cclCommercial: blogCfg.cclCommercial || '1',
                cclDerive: blogCfg.cclDerive || '1',
                thumbnail: thumbnailUrl,
                type: contentType || (cfg.postType || 'post'),
                attachments: '[]',
                recaptchaValue: '',
                draftSequence: null
            };

            // 에디터 번들과 동일한 분기: 신규는 POST /post.json,
            // 수정은 PUT /post/<id>.json. POST로 수정하면 새 글이 생긴다.
            var isUpdate = entryId && entryId !== '0';
            var method = isUpdate ? 'PUT' : 'POST';
            var url = manageUrl + (isUpdate
                ? '/post/' + entryId + '.json'
                : '/post.json');

            fetch(url, {
                method: method,
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
                    url: url,
                    method: method
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

                // script timeout 대비: 결과를 window에 저장
                window.__publishResult = JSON.stringify(result);
                callback(JSON.stringify(result));
            })
            .catch(function(e) {
                var errResult = {
                    success: false, error: 'fetch:' + e.message
                };
                window.__publishResult = JSON.stringify(errResult);
                callback(JSON.stringify(errResult));
            });
        """, title, html_body, tags, blog_name, thumbnail_url, category_id,
            content_type, entry_id, view_channel)

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


def try_publish_via_react_state(
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
            layer_info = publish_verifier.check_publish_layer_opened(sb)
            if layer_info:
                logger.info(f"발행 레이어 열림: {layer_info}")
                # 공개 모드 선택
                form_filler.select_public_mode(sb)
                # 카테고리 선택
                if category_id and category_id != "0":
                    form_filler.select_category_in_layer(sb, category_id)
                time.sleep(1)
                # 발행 확인 버튼 클릭
                return publish_verifier.click_publish_confirm_in_modal(sb, blog_name)
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
