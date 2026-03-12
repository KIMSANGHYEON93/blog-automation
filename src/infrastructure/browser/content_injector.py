"""content_injector — HTML content injection into Tistory WYSIWYG editor."""
from __future__ import annotations

import logging
import time

from src.infrastructure.browser.dom_selectors import (
    TINYMCE_IFRAME_SELECTORS,
    find_element,
)

logger = logging.getLogger(__name__)


def wait_for_wysiwyg_editor(sb, timeout: int = 10) -> None:
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


def inject_html_content(sb, html_text: str) -> bool:
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


def install_ajax_content_interceptor(sb, markdown_text: str) -> None:
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


def ensure_content_in_form(sb, html_text: str) -> None:
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
