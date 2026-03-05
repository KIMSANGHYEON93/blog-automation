"""AdSense 페이지 템플릿 및 렌더링 단위 테스트."""
import re

import pytest

from src.infrastructure.browser.adsense_pages import (
    ADSENSE_PAGES,
    PageSpec,
    render_page_html,
)

# 테스트 공통 파라미터
_BLOG_NAME = "test-blog"
_BLOG_URL = "https://test-blog.tistory.com"
_CONTACT_EMAIL = "test@example.com"
_OWNER_NAME = "테스터"


def _render(page: PageSpec) -> str:
    return render_page_html(
        page,
        blog_name=_BLOG_NAME,
        blog_url=_BLOG_URL,
        contact_email=_CONTACT_EMAIL,
        owner_name=_OWNER_NAME,
    )


class TestAdSensePagesDefined:
    def test_3개_페이지_정의됨(self):
        assert len(ADSENSE_PAGES) == 3

    def test_페이지_제목_목록(self):
        titles = {p.title for p in ADSENSE_PAGES}
        assert "소개" in titles
        assert "개인정보처리방침" in titles
        assert "문의" in titles

    def test_각_템플릿_비어있지_않음(self):
        for page in ADSENSE_PAGES:
            assert page.template.strip(), f"'{page.title}' 템플릿이 비어 있음"


class TestAboutPage:
    @pytest.fixture()
    def html(self):
        page = next(p for p in ADSENSE_PAGES if p.title == "소개")
        return _render(page)

    def test_변수_치환_blog_name(self, html):
        assert _BLOG_NAME in html

    def test_변수_치환_owner_name(self, html):
        assert _OWNER_NAME in html

    def test_변수_치환_contact_email(self, html):
        assert _CONTACT_EMAIL in html


class TestPrivacyPolicyPage:
    @pytest.fixture()
    def html(self):
        page = next(p for p in ADSENSE_PAGES if p.title == "개인정보처리방침")
        return _render(page)

    def test_AdSense_관련_문구(self, html):
        assert "AdSense" in html

    def test_변수_치환_owner_name(self, html):
        assert _OWNER_NAME in html

    def test_변수_치환_contact_email(self, html):
        assert _CONTACT_EMAIL in html


class TestContactPage:
    @pytest.fixture()
    def html(self):
        page = next(p for p in ADSENSE_PAGES if p.title == "문의")
        return _render(page)

    def test_blog_url_포함(self, html):
        assert _BLOG_URL in html

    def test_contact_email_포함(self, html):
        assert _CONTACT_EMAIL in html


class TestHtmlStructure:
    @pytest.mark.parametrize("page", ADSENSE_PAGES, ids=lambda p: p.title)
    def test_div_태그_존재(self, page):
        html = _render(page)
        assert "<div" in html
        assert "</div>" in html

    @pytest.mark.parametrize("page", ADSENSE_PAGES, ids=lambda p: p.title)
    def test_h2_태그_존재(self, page):
        html = _render(page)
        assert "<h2>" in html


class TestNoUnresolvedVars:
    @pytest.mark.parametrize("page", ADSENSE_PAGES, ids=lambda p: p.title)
    def test_미치환_변수_없음(self, page):
        html = _render(page)
        # $로 시작하는 Template 변수가 남아있지 않아야 함
        remaining = re.findall(r"\$[a-z_]+", html)
        assert remaining == [], f"미치환 변수 발견: {remaining}"


class TestPageSpec:
    def test_frozen_dataclass(self):
        page = PageSpec(title="test", template="<p>test</p>")
        with pytest.raises(AttributeError):
            page.title = "changed"  # type: ignore[misc]
