"""내부 링크 자동 삽입 모듈 테스트."""
from __future__ import annotations

from dataclasses import dataclass

from src.infrastructure.seo.internal_linker import inject_internal_links


@dataclass
class FakePost:
    keyword: str = ""
    published_url: str = ""
    row_index: int = 0
    category: str = ""


class TestInjectInternalLinks:
    def test_키워드_매칭_링크_변환(self):
        """본문에 키워드가 있으면 첫 출현만 <a> 태그로 변환."""
        html = "<p>Docker는 컨테이너 기술입니다. Docker를 사용하면 좋습니다.</p>"
        posts = [FakePost(keyword="Docker", published_url="https://blog.com/docker")]
        result = inject_internal_links(html, ["Docker"], posts)
        assert '<a href="https://blog.com/docker">Docker</a>' in result
        # 두 번째 Docker는 변환 안 됨
        assert result.count('<a href="https://blog.com/docker">') == 1

    def test_최대_5개_링크_제한(self):
        """한 글에 최대 5개 내부 링크만 삽입."""
        keywords = [f"kw{i}" for i in range(8)]
        posts = [
            FakePost(keyword=f"kw{i}", published_url=f"https://blog.com/{i}")
            for i in range(8)
        ]
        html = " ".join(f"<p>{kw} 설명입니다.</p>" for kw in keywords)
        result = inject_internal_links(html, keywords, posts)
        assert result.count("<a href=") == 5

    def test_헤더_내부_미변환(self):
        """<h1>~<h3> 내부의 키워드는 변환하지 않는다."""
        html = "<h2>Docker 가이드</h2><p>Docker는 좋습니다.</p>"
        posts = [FakePost(keyword="Docker", published_url="https://blog.com/docker")]
        result = inject_internal_links(html, ["Docker"], posts)
        # h2 내부는 미변환, p 내부만 변환
        assert "<h2>Docker 가이드</h2>" in result
        assert '<a href="https://blog.com/docker">Docker</a>' in result

    def test_코드블록_내부_미변환(self):
        """<code> 내부의 키워드는 변환하지 않는다."""
        html = "<code>Docker run</code><p>Docker를 사용합니다.</p>"
        posts = [FakePost(keyword="Docker", published_url="https://blog.com/docker")]
        result = inject_internal_links(html, ["Docker"], posts)
        assert "<code>Docker run</code>" in result
        assert '<p><a href="https://blog.com/docker">Docker</a>를 사용합니다.</p>' in result

    def test_기존_링크_내부_미변환(self):
        """<a> 태그 내부의 키워드는 변환하지 않는다."""
        html = '<a href="https://other.com">Docker 링크</a><p>Docker 설명.</p>'
        posts = [FakePost(keyword="Docker", published_url="https://blog.com/docker")]
        result = inject_internal_links(html, ["Docker"], posts)
        assert '<a href="https://other.com">Docker 링크</a>' in result

    def test_중복_키워드_첫_출현만(self):
        """같은 키워드가 여러 번 나오면 첫 번째만 변환."""
        html = "<p>Kubernetes는 좋다.</p><p>Kubernetes를 배우자.</p><p>Kubernetes 가이드.</p>"
        posts = [FakePost(keyword="Kubernetes", published_url="https://blog.com/k8s")]
        result = inject_internal_links(html, ["Kubernetes"], posts)
        assert result.count('<a href="https://blog.com/k8s">') == 1

    def test_빈_html_반환(self):
        """빈 HTML이면 그대로 반환."""
        assert inject_internal_links("", ["Docker"], []) == ""

    def test_발행된_포스트_없으면_원본_반환(self):
        """발행된 포스트가 없으면 변환 없이 원본 반환."""
        html = "<p>Docker 설명</p>"
        result = inject_internal_links(html, ["Docker"], [])
        assert result == html

    def test_대소문자_무시_매칭(self):
        """키워드 매칭 시 대소문자 무시."""
        html = "<p>docker는 좋습니다.</p>"
        posts = [FakePost(keyword="Docker", published_url="https://blog.com/docker")]
        result = inject_internal_links(html, ["Docker"], posts)
        assert '<a href="https://blog.com/docker">docker</a>' in result

    def test_키워드_없으면_발행포스트_키워드_사용(self):
        """internal_link_keywords가 빈 리스트면 published_posts 키워드로 fallback."""
        html = "<p>Docker를 사용합니다.</p>"
        posts = [FakePost(keyword="Docker", published_url="https://blog.com/docker")]
        result = inject_internal_links(html, [], posts)
        assert '<a href="https://blog.com/docker">Docker</a>' in result

    def test_pre_태그_내부_미변환(self):
        """<pre> 내부의 키워드는 변환하지 않는다."""
        html = "<pre>Docker run command</pre><p>Docker 가이드.</p>"
        posts = [FakePost(keyword="Docker", published_url="https://blog.com/docker")]
        result = inject_internal_links(html, ["Docker"], posts)
        assert "<pre>Docker run command</pre>" in result
