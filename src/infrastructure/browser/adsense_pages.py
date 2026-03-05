"""AdSense 필수 페이지 자동 발행 — 소개, 개인정보처리방침, 문의."""
from __future__ import annotations

import json as json_mod
import logging
from dataclasses import dataclass
from string import Template

from src.domain.value_objects.publish_result import PublishResult
from src.infrastructure.browser.tistory_editor import _call_tistory_post_api

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageSpec:
    title: str
    template: str


# ---------------------------------------------------------------------------
# 페이지 템플릿 (3개)
# ---------------------------------------------------------------------------

_ABOUT_TEMPLATE = """\
<div class="page-about">
<h2>블로그 소개</h2>
<p><strong>$blog_name</strong>은 IT/개발 분야의 유용한 정보를 공유하는 블로그입니다.</p>

<h2>운영자</h2>
<p>안녕하세요, <strong>$owner_name</strong>입니다.\
 이 블로그를 통해 실무에서 얻은 경험과 지식을 나누고 있습니다.</p>

<h2>다루는 주제</h2>
<ul>
<li>웹 개발 및 프로그래밍</li>
<li>IT 용어 정리 및 비교 분석</li>
<li>트러블슈팅 및 에러 해결</li>
<li>기술 트렌드 및 가이드</li>
</ul>

<h2>연락처</h2>
<p>문의사항은 <a href="mailto:$contact_email">$contact_email</a>로 보내주세요.</p>
</div>"""

_PRIVACY_TEMPLATE = """\
<div class="page-privacy">
<h2>개인정보처리방침</h2>
<p><strong>$blog_name</strong>(이하 "블로그")은 이용자의 개인정보를 중요시하며,\
 관련 법령을 준수합니다.</p>

<h2>수집하는 개인정보 항목</h2>
<p>블로그는 별도의 회원가입 절차 없이 운영되며, 댓글 작성 시 티스토리 플랫폼을\
 통해 닉네임 등 최소한의 정보가 수집될 수 있습니다.</p>

<h2>쿠키(Cookie) 사용</h2>
<p>블로그는 방문자 경험 개선을 위해 쿠키를 사용할 수 있습니다.\
 브라우저 설정에서 쿠키 수집을 거부할 수 있습니다.</p>

<h2>광고</h2>
<p>블로그는 Google AdSense를 통해 광고를 게재할 수 있습니다.\
 Google은 사용자의 관심사에 기반한 광고를 제공하기 위해 쿠키를 사용할 수 있으며,\
 이에 대한 자세한 내용은\
 <a href="https://policies.google.com/technologies/ads" target="_blank">\
Google 광고 정책</a>을 참고해 주세요.</p>

<h2>개인정보보호책임자</h2>
<ul>
<li>성명: $owner_name</li>
<li>이메일: <a href="mailto:$contact_email">$contact_email</a></li>
</ul>

<h2>방침 변경</h2>
<p>본 개인정보처리방침은 법령 및 정책 변경에 따라 수정될 수 있으며,\
 변경 시 블로그를 통해 공지합니다.</p>
</div>"""

_CONTACT_TEMPLATE = """\
<div class="page-contact">
<h2>문의하기</h2>
<p><strong>$blog_name</strong> 블로그에 관심을 가져주셔서 감사합니다.</p>

<h2>연락처</h2>
<p>이메일: <a href="mailto:$contact_email">$contact_email</a></p>

<h2>문의 가능 사항</h2>
<ul>
<li>블로그 콘텐츠 관련 질문</li>
<li>오류 제보 및 수정 요청</li>
<li>협업 및 제휴 문의</li>
<li>기타 건의사항</li>
</ul>

<h2>블로그 주소</h2>
<p><a href="$blog_url" target="_blank">$blog_url</a></p>
</div>"""


ADSENSE_PAGES: list[PageSpec] = [
    PageSpec(title="소개", template=_ABOUT_TEMPLATE),
    PageSpec(title="개인정보처리방침", template=_PRIVACY_TEMPLATE),
    PageSpec(title="문의", template=_CONTACT_TEMPLATE),
]


# ---------------------------------------------------------------------------
# 헬퍼 함수
# ---------------------------------------------------------------------------

def render_page_html(
    page: PageSpec,
    blog_name: str,
    blog_url: str,
    contact_email: str,
    owner_name: str,
) -> str:
    """템플릿 변수를 치환하여 HTML 문자열 반환."""
    return Template(page.template).safe_substitute(
        blog_name=blog_name,
        blog_url=blog_url,
        contact_email=contact_email,
        owner_name=owner_name,
    )


def _check_existing_pages(sb, blog_name: str) -> set[str]:
    """GET /manage/pages.json XHR로 기존 페이지 제목 목록 조회.

    실패 시 빈 set 반환 (발행 계속 진행).
    """
    try:
        result_json = sb.execute_script("""
            var blogName = arguments[0];
            var manageUrl = '';
            if (window.appInfo && window.appInfo.manageUrl) {
                manageUrl = window.appInfo.manageUrl;
            } else {
                manageUrl = 'https://' + blogName + '.tistory.com/manage';
            }
            var url = manageUrl + '/pages.json';
            var xhr = new XMLHttpRequest();
            xhr.open('GET', url, false);
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            try {
                xhr.send();
            } catch(e) {
                return JSON.stringify({success: false, error: e.message});
            }
            if (xhr.status >= 200 && xhr.status < 300) {
                return xhr.responseText;
            }
            return JSON.stringify({
                success: false, status: xhr.status
            });
        """, blog_name)

        if not result_json:
            return set()

        data = json_mod.loads(result_json)
        # pages.json 응답 구조: {items: [{title: "...", ...}, ...]}
        items = data.get("items") or data.get("posts") or []
        return {item.get("title", "") for item in items if item.get("title")}
    except Exception as e:
        logger.warning(f"기존 페이지 목록 조회 실패 (무시): {e}")
        return set()


# ---------------------------------------------------------------------------
# 메인 진입점
# ---------------------------------------------------------------------------

def publish_pages(
    sb,
    blog_name: str,
    contact_email: str,
    owner_name: str,
) -> list[PublishResult]:
    """3개 AdSense 필수 페이지를 순서대로 발행. 이미 존재하는 페이지는 건너뜀."""
    blog_url = f"https://{blog_name}.tistory.com"

    # 에디터 페이지 열기 (XHR 컨텍스트용 — window.appInfo 등 로드)
    editor_url = f"{blog_url}/manage/newpost"
    sb.open(editor_url)
    import time
    time.sleep(2)

    # 기존 페이지 확인 (중복 발행 방지)
    existing_titles = _check_existing_pages(sb, blog_name)
    if existing_titles:
        logger.info(f"기존 페이지 감지: {existing_titles}")

    results: list[PublishResult] = []

    for page in ADSENSE_PAGES:
        if page.title in existing_titles:
            logger.info(f"페이지 '{page.title}' 이미 존재 — 건너뜀")
            results.append(PublishResult.ok(url="", entry_id=""))
            continue

        html = render_page_html(
            page, blog_name, blog_url, contact_email, owner_name,
        )

        api_result = _call_tistory_post_api(
            sb,
            blog_name=blog_name,
            title=page.title,
            html_body=html,
            tags="",
            thumbnail_url="",
            category_id="0",
            content_type="page",
        )

        if api_result:
            entry_url, entry_id = api_result
            logger.info(f"페이지 '{page.title}' 발행 완료: {entry_url}")
            results.append(PublishResult.ok(url=entry_url, entry_id=entry_id))
        else:
            logger.error(f"페이지 '{page.title}' 발행 실패")
            results.append(PublishResult.fail(error=f"페이지 발행 실패: {page.title}"))

        # 페이지 간 짧은 딜레이
        time.sleep(3)

    return results
