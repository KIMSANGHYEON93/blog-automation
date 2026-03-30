"""TistoryEditor — Tistory blog editor automation (2026-03-02 updated).

변경 이력:
  2026-03-13 — 모듈 분리: 6개 서브모듈로 함수 위임 (orchestrator only)
  2026-03-02 — 일일 발행 제한 감지 + 배치 중단 (DailyPublishLimitError)
  2026-03-02 — 발행 후 HTTP 검증 + 비공개 자동 복구 (_verify / _fix_post_visibility)
  2026-03-01 — MD→HTML 변환: 마크다운 모드 대신 WYSIWYG 모드에서 HTML 주입 (방향 A)
  2026-02-28 — 비공개→공개 발행 전환
"""
from __future__ import annotations

import logging
import random as _rnd
import time

from src.domain.entities.post import Post
from src.domain.value_objects.publish_result import PublishResult
from src.domain.value_objects.site_profile import CategoryMapping, SiteProfile
from src.infrastructure.browser import (
    api_publisher,
    content_injector,
    form_filler,
    html_transformer,
    markdown_converter,
    publish_verifier,
)
from src.infrastructure.browser.dom_selectors import (
    EDITOR_PATH,
    TITLE_SELECTORS,
    find_element,
)
from src.infrastructure.seo.html_optimizer import optimize_html
from src.infrastructure.seo.inline_styler import apply_inline_styles

logger = logging.getLogger(__name__)

_DAILY_LIMIT_PATTERN = "최대 15개까지"

# 모듈 수준 SiteProfile — set_site_profile()로 주입, 미설정 시 하위 호환 기본값 사용
# NOTE: 글로벌 상태 deprecated. 새 코드는 publish_post/update_post에 profile 인자 전달.
_site_profile: SiteProfile | None = None

_DEFAULT_PROFILE = SiteProfile(
    blog_niche="B2B IT 블로그",
    default_category_id="966384",
    default_view_channel="401",
    categories=(
        CategoryMapping(name="용어", tistory_id="991463", view_channel="401",
                        aliases=("용어정리", "개념"),
                        keyword_patterns=("란$", "이란$", "뜻$", "의미$")),
        CategoryMapping(name="비교", tistory_id="984395", view_channel="401",
                        keyword_patterns=("vs ", "비교$", "차이$")),
        CategoryMapping(name="트러블슈팅", tistory_id="966385", view_channel="401",
                        aliases=("에러", "오류", "에러 해결"),
                        keyword_patterns=("에러$", "오류$", "해결$", "안될때$")),
        CategoryMapping(name="AI", tistory_id="993759", view_channel="401",
                        aliases=("인공지능",),
                        keyword_patterns=("AI ", "인공지능", "LLM", "GPT",
                                          "머신러닝", "딥러닝", "ChatGPT")),
        CategoryMapping(name="Windows", tistory_id="983175", view_channel="401",
                        aliases=("윈도우",),
                        keyword_patterns=("윈도우", "Windows ", "윈도우즈")),
        CategoryMapping(name="Linux", tistory_id="998284", view_channel="401",
                        aliases=("리눅스",),
                        keyword_patterns=("리눅스", "Linux ", "우분투",
                                          "CentOS", "Ubuntu")),
        CategoryMapping(name="가이드", tistory_id="966384", view_channel="401",
                        aliases=("튜토리얼",),
                        keyword_patterns=("방법$", "설정$", "설치$", "가이드$")),
        CategoryMapping(name="트렌드", tistory_id="966384", view_channel="401",
                        aliases=("동향",),
                        keyword_patterns=("트렌드$", "전망$")),
    ),
)


def set_site_profile(profile: SiteProfile) -> None:
    """SiteProfile 주입. CLI에서 호출.

    .. deprecated::
        새 코드는 SeleniumBrowserAdapter 생성자에 profile을 전달하세요.
    """
    global _site_profile  # noqa: PLW0603
    _site_profile = profile


def _get_profile(profile: SiteProfile | None = None) -> SiteProfile:
    """SiteProfile 반환. 인자 > 모듈 글로벌 > 기본값 순서."""
    if profile is not None:
        return profile
    return _site_profile if _site_profile is not None else _DEFAULT_PROFILE


def _resolve_category_id(category_name: str, profile: SiteProfile | None = None) -> str:
    """카테고리 이름을 Tistory 카테고리 ID로 변환."""
    return _get_profile(profile).resolve_category_id(category_name)


def publish_post(
    sb, post: Post, blog_name: str, profile: SiteProfile | None = None,
) -> PublishResult:
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

        # 에디터 페이지 열기 (같은 URL 재방문 시 강제 리로드)
        write_url = f"https://{blog_name}.tistory.com{EDITOR_PATH}"
        fresh_url = f"{write_url}?_t={int(time.time())}{_rnd.randint(0, 999)}"
        sb.open(fresh_url)
        time.sleep(5)

        # async script timeout 확장 (Fetch API 호출 대기용)
        # sb.open() 이후에 설정해야 SeleniumBase가 리셋하지 않음
        with contextlib.suppress(Exception):
            sb.driver.set_script_timeout(120)

        # 에디터 로드 대기 (제목 입력창 DOM 존재 확인)
        title_sel = find_element(sb, TITLE_SELECTORS, timeout=15)
        if not title_sel:
            return PublishResult.fail("제목 입력창을 찾을 수 없음")

        # 제목 입력 (JS fallback 포함)
        title_text = content.title_or_fallback(post.keyword)
        form_filler.safe_click(sb, title_sel)
        if not form_filler.safe_type(sb, title_sel, title_text):
            return PublishResult.fail("제목 입력 실패")
        time.sleep(0.5)

        # --- MD→HTML 변환 (방향 A: Python 측 변환 후 WYSIWYG 모드 주입) ---
        html_body = markdown_converter.convert_markdown_to_html(body_markdown)

        # 이미지 lazy loading 적용
        html_body = html_transformer.add_lazy_loading(html_body)

        # 외부 링크에 nofollow/noopener 속성 추가
        html_body = html_transformer.add_nofollow_to_external_links(html_body, blog_name)

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
        if not html_transformer.validate_html(html_body):
            logger.warning("HTML 변환 검증 실패 — 그대로 진행")

        # FAQ LD+JSON 스키마 주입 (HTML 본문 하단에 추가)
        faq_ld_json = content.faq_ld_json() if hasattr(content, 'faq_ld_json') else ""
        if faq_ld_json:
            html_body = html_transformer.append_faq_schema(html_body, faq_ld_json)

        # 반응형 + 성능 최적화 (img lazy/decoding, iframe lazy, preconnect)
        html_body = optimize_html(html_body)
        html_body = apply_inline_styles(html_body)

        # [마크다운 모드 전환 — 비활성화: WYSIWYG 기본모드 사용]
        # sb.execute_script("window.confirm = function() { return true; };")
        # _switch_to_markdown_mode(sb)
        # time.sleep(2)

        # WYSIWYG 에디터 로드 대기
        content_injector.wait_for_wysiwyg_editor(sb)

        # AJAX 인터셉터 설치 (save/publish 요청에 빈 content → 실제 HTML 교체)
        content_injector.install_ajax_content_interceptor(sb, html_body)

        # HTML 본문 주입 (WYSIWYG 모드: TinyMCE / iframe / textarea)
        if not content_injector.inject_html_content(sb, html_body):
            return PublishResult.fail("HTML 본문 주입 실패")
        time.sleep(2)

        # 태그 입력
        if content.tags:
            form_filler.input_tags(sb, content.tag_list())
            time.sleep(1)

        # 메타 설명(meta description) 주입
        if content.meta_description:
            form_filler.inject_meta_description(sb, content.meta_description)
            time.sleep(0.5)

        # 저장 전 콘텐츠 동기화 확인
        content_injector.ensure_content_in_form(sb, html_body)

        # 직접 API 호출로 발행 (UI 버튼 클릭 대신)
        api_result = _publish_via_api(
            sb, blog_name, content, html_body, post, profile,
        )
        if not api_result:
            return PublishResult.fail("API 발행 실패 — 모든 방법 실패")

        published_url, entry_id = api_result
        logger.info(f"API 발행 완료: {post.keyword} → {published_url} (id={entry_id})")

        # --- 발행 후 공개 상태 검증 ---
        http_code = publish_verifier.verify_published_url(published_url)
        if http_code == 200:
            logger.info(f"공개 검증 성공 (200): {published_url}")
            # FAQ 스키마 검증 (경고 로그만, 실패 안 함)
            faq_ld_json = content.faq_ld_json() if hasattr(content, 'faq_ld_json') else ""
            if faq_ld_json:
                has_faq = publish_verifier.verify_faq_schema(published_url)
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
            fixed = publish_verifier.fix_post_visibility(sb, blog_name, published_url)
            if fixed:
                recheck = publish_verifier.verify_published_url(published_url)
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


def update_post(
    sb, post: Post, blog_name: str, profile: SiteProfile | None = None,
) -> PublishResult:
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

        write_url = f"https://{blog_name}.tistory.com{EDITOR_PATH}"
        fresh_url = f"{write_url}?_t={int(time.time())}{_rnd.randint(0, 999)}"
        sb.open(fresh_url)
        time.sleep(5)

        # async script timeout 확장 (Fetch API 호출 대기용)
        # sb.open() 이후에 설정해야 SeleniumBase가 리셋하지 않음
        with contextlib.suppress(Exception):
            sb.driver.set_script_timeout(120)

        # MD→HTML 변환 (publish_post와 동일 파이프라인)
        html_body = markdown_converter.convert_markdown_to_html(body_markdown)
        html_body = html_transformer.add_lazy_loading(html_body)
        html_body = html_transformer.add_nofollow_to_external_links(html_body, blog_name)

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
            html_body = html_transformer.append_faq_schema(html_body, faq_ld_json)

        # 반응형 + 성능 최적화
        html_body = optimize_html(html_body)
        html_body = apply_inline_styles(html_body)

        # API 호출로 수정 (entry_id 전달)
        title = content.title_or_fallback(post.keyword)
        tags = ",".join(content.tag_list()) if content.tags else ""
        thumbnail_url = content.thumbnail_url if content.thumbnail_url else ""
        if not thumbnail_url:
            thumbnail_url = html_transformer.extract_first_image_url(html_body)
        category_id = _resolve_category_id(post.category, profile)
        view_channel = ""
        if profile:
            view_channel = profile.resolve_view_channel(post.category)

        api_result = api_publisher.call_tistory_post_api(
            sb, blog_name, title, html_body, tags, thumbnail_url,
            category_id, entry_id=post.entry_id,
            view_channel=view_channel,
        )
        if not api_result:
            return PublishResult.fail("API 수정 실패")

        published_url, entry_id = api_result
        logger.info(f"API 수정 완료: {post.keyword} → {published_url} (id={entry_id})")

        # 공개 상태 검증
        http_code = publish_verifier.verify_published_url(published_url)
        if http_code == 200:
            logger.info(f"공개 검증 성공 (200): {published_url}")
            return PublishResult.ok(published_url, entry_id=entry_id)

        if http_code in (403, 404):
            logger.warning(f"수정 URL 비공개 감지 ({http_code}): {published_url}")
            fixed = publish_verifier.fix_post_visibility(sb, blog_name, published_url)
            if fixed:
                recheck = publish_verifier.verify_published_url(published_url)
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
    profile: SiteProfile | None = None,
) -> tuple[str, str] | None:
    """직접 API 호출로 포스트 발행 (React UI 버튼 클릭 대신).

    Tistory 에디터 내부 API: POST {manageUrl}/post.json
    성공 시 (발행 URL, entry_id) 튜플 반환, 실패 시 None.
    """
    title = content.title_or_fallback(post.keyword)
    tags = ",".join(content.tag_list()) if content.tags else ""
    thumbnail_url = content.thumbnail_url if content.thumbnail_url else ""
    if not thumbnail_url:
        thumbnail_url = html_transformer.extract_first_image_url(html_body)
        if thumbnail_url:
            logger.info(f"대표이미지 자동 선택: {thumbnail_url[:80]}")
    category_id = _resolve_category_id(post.category, profile)
    view_channel = ""
    if profile:
        view_channel = profile.resolve_view_channel(post.category)
    logger.info(
        f"카테고리 해석: '{post.category}' → ID {category_id}, 홈주제={view_channel}"
    )

    # 방법 1: 직접 XHR API 호출 (visibility=20 명시적 전송, 가장 신뢰도 높음)
    api_result = api_publisher.call_tistory_post_api(
        sb, blog_name, title, html_body, tags, thumbnail_url, category_id,
        view_channel=view_channel,
    )
    if api_result:
        return api_result

    # 방법 2: React 내부 상태를 통한 발행 (API 실패 시 fallback)
    react_url = api_publisher.try_publish_via_react_state(
        sb, title, html_body, tags, blog_name, category_id,
    )
    if react_url:
        # URL이 올바른 블로그인지 검증
        if blog_name in react_url:
            return (react_url, "")
        logger.warning(
            f"React fallback URL이 다른 블로그: {react_url} "
            f"(expected: {blog_name}.tistory.com)"
        )
        # 관리 페이지에서 올바른 URL 재탐색
        correct_url = publish_verifier.extract_published_url(sb, blog_name)
        if correct_url and blog_name in correct_url:
            logger.info(f"관리 페이지에서 올바른 URL 발견: {correct_url}")
            return (correct_url, "")
        # 최후 수단: blog_name 기반 URL 구성 (발행은 됐으므로)
        logger.warning("올바른 URL 추출 불가 — 관리 페이지에서 수동 확인 필요")
        return (f"https://{blog_name}.tistory.com", "")

    return None
