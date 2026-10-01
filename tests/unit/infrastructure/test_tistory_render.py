"""티스토리 본문 변환 — 발행·수정 발행·미리보기가 같은 함수를 쓴다."""
from __future__ import annotations

from pathlib import Path

from src.domain.entities.post import Post
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.browser.html_transformer import append_naver_cta
from src.infrastructure.browser.tistory_render import render_tistory_html

GOLDEN = Path(__file__).resolve().parents[2] / "fixtures" / "tistory_render_golden.html"
BODY = (
    "## IaC란?\n\nIaC는 인프라를 코드로 관리합니다. Terraform을 많이 씁니다.\n\n"
    "![다이어그램](https://example.com/a.png)\n\n"
    "## 작동 원리\n\n### 선언형\n\n원하는 상태를 적습니다. "
    "[공식 문서](https://developer.hashicorp.com/terraform)\n\n"
    "```python\nprint('hi')\n```\n\n"
    "| 도구 | 방식 |\n|---|---|\n| Terraform | 선언형 |\n\n"
    "## FAQ\n\n**Q. 어렵나요?**\n\n아닙니다.\n"
)


def sample_post() -> Post:
    post = Post(
        row_index=7, keyword="IaC란", status=PostStatus.PENDING,
        content=PostContent(
            title="IaC란? 개념 정리", body_markdown=BODY,
            meta_description="IaC 개념과 작동 원리를 정리했습니다.",
            faq_schema='[{"question": "어렵나요?", "answer": "아닙니다."}]',
            internal_link_keywords='["Terraform"]',
        ),
        quality_score=90,
    )
    post.internal_link_map = {"Terraform": "https://kimsanghyeon.tistory.com/100"}
    return post


def test_변환_결과는_골든_파일과_같다():
    assert render_tistory_html(sample_post(), "kimsanghyeon") == GOLDEN.read_text(encoding="utf-8")


def test_내부_링크_매핑이_없으면_링크를_넣지_않는다():
    post = sample_post()
    post.internal_link_map = None
    assert "kimsanghyeon.tistory.com/100" not in render_tistory_html(post, "kimsanghyeon")


CTA_URL = "https://blog.naver.com/sangpedia"


def test_CTA_주소가_없으면_그대로():
    assert append_naver_cta("<p>본문</p>", "") == "<p>본문</p>"


def test_CTA_블록은_문구와_새_탭_링크를_가진다():
    html = append_naver_cta("<p>본문</p>", CTA_URL)
    assert html.startswith("<p>본문</p>")
    assert 'href="https://blog.naver.com/sangpedia"' in html
    assert 'target="_blank"' in html and 'rel="noopener"' in html
    assert "IT·AI 실무 글을 네이버 블로그에도 올립니다. 이웃 추가하고 새 글 받아 보세요." in html
    assert ">네이버 블로그 이웃 추가</a>" in html


def test_CTA_주소는_이스케이프한다():
    assert '"><script>' not in append_naver_cta("<p>x</p>", 'https://x/"><script>')


def test_렌더링하면_CTA가_맨_끝에_붙는다():
    html = render_tistory_html(sample_post(), "kimsanghyeon", CTA_URL)
    assert html.rstrip().endswith("</div>")
    assert html.rfind("네이버 블로그 이웃 추가") > html.rfind("application/ld+json")


def test_CTA가_없으면_골든_그대로():
    assert render_tistory_html(sample_post(), "kimsanghyeon", "") == GOLDEN.read_text(
        encoding="utf-8"
    )
