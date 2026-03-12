"""form_filler — DOM interaction for Tistory editor form fields."""
from __future__ import annotations

import logging
import time

from src.infrastructure.browser.dom_selectors import (
    TAG_INPUT_SELECTORS,
    find_element,
)

logger = logging.getLogger(__name__)


def safe_click(sb, selector: str) -> bool:
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


def safe_type(sb, selector: str, text: str) -> bool:
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


def select_category_in_layer(sb, category_id: str) -> None:
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


def select_public_mode(sb) -> None:
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


def input_tags(sb, tags: list[str]) -> None:
    """태그 입력 (개별 태그를 Enter 키로 등록)."""
    try:
        tag_sel = find_element(sb, TAG_INPUT_SELECTORS, timeout=5)
        if not tag_sel:
            logger.warning("태그 입력창을 찾을 수 없음")
            return

        for tag in tags:
            safe_click(sb, tag_sel)
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


def inject_meta_description(sb, meta_description: str) -> None:
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
