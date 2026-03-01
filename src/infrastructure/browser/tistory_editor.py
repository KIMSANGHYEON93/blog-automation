"""TistoryEditor — Tistory blog editor automation (2026-03-01 updated).

변경 이력:
  2026-03-01 — MD→HTML 변환: 마크다운 모드 대신 WYSIWYG 모드에서 HTML 주입 (방향 A)
  2026-02-28 — 비공개→공개 발행 전환
"""
from __future__ import annotations

import logging
import re
import time

import markdown as md_lib

from src.domain.entities.post import Post
from src.domain.value_objects.publish_result import PublishResult
from src.infrastructure.browser.dom_selectors import (
    CONTENT_AREA_SELECTORS,
    EDITOR_PATH,
    MARKDOWN_MODE_SELECTORS,
    MODE_CONFIRM_SELECTORS,
    MODE_SWITCH_BUTTON_SELECTORS,
    PUBLIC_MODE_SELECTORS,
    PUBLISH_BUTTON_SELECTORS,
    PUBLISH_CONFIRM_SELECTORS,
    SAVE_BUTTON_SELECTORS,
    TAG_INPUT_SELECTORS,
    TINYMCE_IFRAME_SELECTORS,
    TITLE_SELECTORS,
    find_element,
)

logger = logging.getLogger(__name__)


def publish_post(sb, post: Post, blog_name: str) -> PublishResult:
    """티스토리 에디터에 포스트 발행. PublishResult 반환."""
    try:
        if post.content is None or not post.content.body_markdown:
            return PublishResult.fail("포스트 콘텐츠가 없음")

        content = post.content
        body_markdown: str = content.body_markdown or ""

        # 에디터 페이지 열기
        write_url = f"https://{blog_name}.tistory.com{EDITOR_PATH}"
        sb.open(write_url)
        time.sleep(3)

        # 제목 입력
        title_sel = find_element(sb, TITLE_SELECTORS)
        if not title_sel:
            return PublishResult.fail("제목 입력창을 찾을 수 없음")
        sb.click(title_sel)
        sb.type(title_sel, content.title_or_fallback(post.keyword))
        time.sleep(0.5)

        # --- MD→HTML 변환 (방향 A: Python 측 변환 후 WYSIWYG 모드 주입) ---
        html_body = convert_markdown_to_html(body_markdown)

        # 이미지 lazy loading 적용
        html_body = _add_lazy_loading(html_body)

        # 외부 링크에 nofollow/noopener 속성 추가
        html_body = _add_nofollow_to_external_links(html_body, blog_name)

        # HTML 변환 검증
        if not validate_html(html_body):
            logger.warning("HTML 변환 검증 실패 — 그대로 진행")

        # FAQ LD+JSON 스키마 주입 (HTML 본문 하단에 추가)
        faq_ld_json = content.faq_ld_json() if hasattr(content, 'faq_ld_json') else ""
        if faq_ld_json:
            html_body = _append_faq_schema(html_body, faq_ld_json)

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

        # Step 1: 임시저장 (내용을 서버에 저장)
        save_sel = find_element(sb, SAVE_BUTTON_SELECTORS, timeout=5)
        if save_sel:
            sb.click(save_sel)
            time.sleep(3)
            logger.info(f"임시저장 완료: {post.keyword}")
        else:
            logger.warning("임시저장 버튼을 찾을 수 없음")

        # Step 2: 발행 설정 레이어 열기 (완료 버튼)
        publish_sel = find_element(sb, PUBLISH_BUTTON_SELECTORS, timeout=5)
        if publish_sel:
            sb.click(publish_sel)
            time.sleep(2)
            logger.info(f"발행 설정 레이어 열기: {post.keyword}")

            # Step 2.5: 공개 모드 선택
            _select_public_mode(sb)
            time.sleep(1)

            # 발행 전 콘텐츠 재동기화
            _ensure_content_in_form(sb, body_markdown)

            # Step 3: 최종 발행 확인 버튼 클릭
            confirm_sel = find_element(sb, PUBLISH_CONFIRM_SELECTORS, timeout=10)
            if confirm_sel:
                sb.click(confirm_sel)
                time.sleep(3)
                logger.info(f"공개 발행 확인 버튼 클릭: {post.keyword}")
            else:
                # JS fallback: 발행 버튼 직접 클릭
                clicked = sb.execute_script("""
                    var selectors = ['#publish-btn', '.btn_publish',
                        '.layer_post .btn_ok', 'button.btn_default'];
                    for (var i = 0; i < selectors.length; i++) {
                        var el = document.querySelector(selectors[i]);
                        if (el) { el.click(); return selectors[i]; }
                    }
                    return null;
                """)
                if clicked:
                    time.sleep(3)
                    logger.info(f"JS fallback 발행 확인 클릭: {clicked}")
                else:
                    logger.warning("발행 확인 버튼을 찾을 수 없음 — 레이어만 열림")
        else:
            logger.warning("발행 버튼(완료)을 찾을 수 없음")

        time.sleep(3)
        current_url = sb.get_current_url()

        # 발행 후 실제 글 URL 추출
        post_url = current_url
        if "/manage/" in current_url:
            extracted = _extract_published_url(sb, blog_name)
            if extracted:
                post_url = extracted
                logger.info(f"발행 완료: {post.keyword} → {post_url}")
            else:
                logger.warning(f"발행 URL 추출 실패, 관리 페이지 URL 사용: {current_url}")
        else:
            logger.info(f"발행 성공: {post.keyword} → {post_url}")

        return PublishResult.ok(post_url)

    except Exception as e:
        logger.error(f"발행 실패: {post.keyword} — {e}")
        return PublishResult.fail(str(e))


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


def convert_markdown_to_html(md_text: str) -> str:
    """마크다운 텍스트를 HTML로 변환.

    Extensions: tables, fenced_code, nl2br, sane_lists, codehilite, toc
    - codehilite: noclasses=True → 인라인 스타일 (외부 CSS 불필요)
    - toc: H2~H3 목차 자동 생성, 첫 번째 <h2> 앞에 삽입
    """
    if not md_text or not md_text.strip():
        return ""
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

    return html_body


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
    """발행 설정 레이어에서 공개 모드를 선택."""
    try:
        # 방법 1: CSS/XPath 셀렉터로 공개 라디오 버튼 클릭
        public_sel = find_element(sb, PUBLIC_MODE_SELECTORS, timeout=3)
        if public_sel:
            sb.click(public_sel)
            logger.info(f"공개 모드 선택: {public_sel}")
            return

        # 방법 2: JS로 공개 라디오 버튼 선택
        clicked = sb.execute_script("""
            // value=0이 공개, value=1이 보호, value=3이 비공개
            var radios = document.querySelectorAll(
                'input[name="visibility"], input[name="openType"]'
            );
            for (var i = 0; i < radios.length; i++) {
                if (radios[i].value === '0' || radios[i].value === '20') {
                    radios[i].checked = true;
                    radios[i].click();
                    radios[i].dispatchEvent(
                        new Event('change', {bubbles: true})
                    );
                    return 'selected: ' + radios[i].id;
                }
            }
            // label 텍스트로 찾기
            var labels = document.querySelectorAll('label');
            for (var j = 0; j < labels.length; j++) {
                if (labels[j].textContent.trim() === '공개') {
                    labels[j].click();
                    return 'clicked label: 공개';
                }
            }
            return null;
        """)
        if clicked:
            logger.info(f"JS로 공개 모드 선택: {clicked}")
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


def _input_tags(sb, tags: list[str]) -> None:
    """태그 입력 (개별 태그를 Enter 키로 등록)."""
    try:
        tag_sel = find_element(sb, TAG_INPUT_SELECTORS, timeout=5)
        if not tag_sel:
            logger.warning("태그 입력창을 찾을 수 없음")
            return

        for tag in tags:
            sb.click(tag_sel)
            time.sleep(0.3)
            sb.type(tag_sel, tag + "\n")
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
