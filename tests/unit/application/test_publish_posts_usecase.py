"""Unit tests for PublishPostsUseCase — TDD RED phase."""

from src.application.use_cases.publish_posts import PublishPostsUseCase
from src.domain.entities.post import Post
from src.domain.exceptions import DailyPublishLimitError
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.browser.mock_browser import MockBrowserAdapter
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


def make_publishable_post(row_index: int = 1, keyword: str = "AD란"):
    return Post(
        row_index=row_index,
        keyword=keyword,
        status=PostStatus.PENDING,
        content=PostContent(title="테스트 제목", body_markdown="## 내용\n본문"),
    )


class TestPublishPostsNormalFlow:
    """정상 발행 흐름 테스트."""

    def test_2건_정상_발행(self):
        posts = [make_publishable_post(1, "AD란"), make_publishable_post(2, "SSO란")]
        repo = InMemoryPostRepository(posts)
        browser = MockBrowserAdapter(
            login_success=True, publish_url="https://test.tistory.com/1"
        )
        use_case = PublishPostsUseCase(repo=repo, browser=browser)

        stats = use_case.execute()

        assert stats.published == 2
        assert stats.failed == 0
        assert browser.stopped is True

    def test_발행_후_상태_PUBLISHED(self):
        post = make_publishable_post(1)
        repo = InMemoryPostRepository([post])
        browser = MockBrowserAdapter(publish_url="https://test.tistory.com/99")
        use_case = PublishPostsUseCase(repo=repo, browser=browser)

        use_case.execute()

        saved = repo.all()[0]
        assert saved.status == PostStatus.PUBLISHED
        assert saved.published_url == "https://test.tistory.com/99"


class TestPublishPostsSkip:
    """본문 없는 포스트 건너뛰기."""

    def test_본문_없는_포스트_건너뛰기(self):
        post = Post(
            row_index=1,
            keyword="AD란",
            status=PostStatus.PENDING,
            content=PostContent(title="제목", body_markdown=""),
        )
        repo = InMemoryPostRepository([post])
        browser = MockBrowserAdapter()
        use_case = PublishPostsUseCase(repo=repo, browser=browser)

        stats = use_case.execute()

        assert stats.skipped == 1
        assert stats.published == 0

    def test_content_None_건너뛰기(self):
        post = Post(row_index=1, keyword="AD란", status=PostStatus.PENDING)
        repo = InMemoryPostRepository([post])
        browser = MockBrowserAdapter()
        use_case = PublishPostsUseCase(repo=repo, browser=browser)

        stats = use_case.execute()

        assert stats.skipped == 1


class TestPublishPostsFailure:
    """발행 실패 처리."""

    def test_발행_실패_시_FAILED_상태(self):
        post = make_publishable_post()
        repo = InMemoryPostRepository([post])
        browser = MockBrowserAdapter(publish_error="에디터 로딩 실패")
        use_case = PublishPostsUseCase(repo=repo, browser=browser)

        stats = use_case.execute()

        assert stats.failed == 1
        saved = repo.all()[0]
        assert saved.status == PostStatus.FAILED
        assert "에디터 로딩 실패" in saved.error_message

    def test_로그인_실패_즉시_중단(self):
        posts = [make_publishable_post(1), make_publishable_post(2)]
        repo = InMemoryPostRepository(posts)
        browser = MockBrowserAdapter(login_success=False)
        use_case = PublishPostsUseCase(repo=repo, browser=browser)

        stats = use_case.execute()

        assert stats.published == 0
        assert len(browser.published_posts) == 0
        assert browser.stopped is True


class TestPublishPostsBrowserLifecycle:
    """브라우저 생명주기 관리."""

    def test_예외_발생_시_브라우저_종료(self):
        class BuggyBrowser(MockBrowserAdapter):
            def publish(self, post):
                raise RuntimeError("예상치 못한 오류")

        post = make_publishable_post()
        repo = InMemoryPostRepository([post])
        browser = BuggyBrowser()
        use_case = PublishPostsUseCase(repo=repo, browser=browser)

        use_case.execute()

        assert browser.stopped is True

    def test_빈_목록일_때_브라우저_미시작(self):
        repo = InMemoryPostRepository([])
        browser = MockBrowserAdapter()
        use_case = PublishPostsUseCase(repo=repo, browser=browser)

        stats = use_case.execute()

        assert stats.published == 0
        assert stats.skipped == 0
        assert browser.started is False


class TestPublishPostsDailyLimit:
    """일일 발행 제한 처리."""

    def test_일일_제한_시_나머지_건너뛰기(self):
        """2번째 글에서 일일 제한 발생 시 3번째 글은 시도하지 않음."""

        class DailyLimitBrowser(MockBrowserAdapter):
            call_count = 0

            def publish(self, post):
                self.call_count += 1
                if self.call_count >= 2:
                    raise DailyPublishLimitError("최대 15개까지")
                return super().publish(post)

        posts = [make_publishable_post(i, f"kw{i}") for i in range(1, 4)]
        repo = InMemoryPostRepository(posts)
        browser = DailyLimitBrowser(publish_url="https://test.tistory.com/1")
        use_case = PublishPostsUseCase(repo=repo, browser=browser, max_posts=5)

        stats = use_case.execute()

        assert stats.published == 1
        assert stats.failed == 0
        # 2번째 글은 PENDING으로 복원 (일일 제한이므로 실패 아님)
        assert repo.all()[1].status == PostStatus.PENDING
        # 3번째 글은 시도조차 안 함
        assert repo.all()[2].status == PostStatus.PENDING
        assert browser.stopped is True

    def test_일일_제한_포스트_발행대기_복원(self):
        """일일 제한 걸린 포스트가 PUBLISHING→PENDING으로 복원."""

        class ImmediateLimitBrowser(MockBrowserAdapter):
            def publish(self, post):
                raise DailyPublishLimitError("최대 15개까지")

        post = make_publishable_post()
        repo = InMemoryPostRepository([post])
        browser = ImmediateLimitBrowser()
        use_case = PublishPostsUseCase(repo=repo, browser=browser)

        stats = use_case.execute()

        assert stats.published == 0
        assert stats.failed == 0
        saved = repo.all()[0]
        assert saved.status == PostStatus.PENDING


class TestRelatedLinks:
    """관련 글 자동 삽입 테스트."""

    def _make_published_post(
        self, row_index: int, keyword: str, category: str = "IT",
        url: str = "https://test.tistory.com/1",
    ) -> Post:
        post = Post(
            row_index=row_index,
            keyword=keyword,
            category=category,
            status=PostStatus.PUBLISHED,
            content=PostContent(title=keyword, body_markdown="본문"),
            published_url=url,
        )
        return post

    def test_관련_글_삽입_동일_카테고리(self):
        """동일 카테고리 발행글이 있으면 관련 글 HTML이 body에 포함된다."""
        pending = Post(
            row_index=10,
            keyword="AD란",
            category="IT",
            status=PostStatus.PENDING,
            content=PostContent(title="AD란", body_markdown="## AD\n본문"),
        )
        pub1 = self._make_published_post(1, "SSO란", "IT", "https://test.tistory.com/1")
        pub2 = self._make_published_post(2, "LDAP란", "IT", "https://test.tistory.com/2")

        repo = InMemoryPostRepository([pending, pub1, pub2])
        browser = MockBrowserAdapter(publish_url="https://test.tistory.com/10")
        use_case = PublishPostsUseCase(repo=repo, browser=browser)

        use_case.execute()

        saved = repo.all()[0]
        assert "관련 글" in saved.content.body_markdown
        assert "SSO란" in saved.content.body_markdown
        assert "LDAP란" in saved.content.body_markdown

    def test_관련_글_미삽입_발행글_없음(self):
        """발행글 0건이면 관련 글 섹션이 생성되지 않는다."""
        pending = Post(
            row_index=10,
            keyword="AD란",
            category="IT",
            status=PostStatus.PENDING,
            content=PostContent(title="AD란", body_markdown="## AD\n본문"),
        )
        repo = InMemoryPostRepository([pending])
        browser = MockBrowserAdapter(publish_url="https://test.tistory.com/10")
        use_case = PublishPostsUseCase(repo=repo, browser=browser)

        use_case.execute()

        saved = repo.all()[0]
        assert "관련 글" not in saved.content.body_markdown

    def test_관련_글_자기자신_제외(self):
        """현재 발행하려는 포스트는 관련 글 목록에서 제외된다."""
        pending = Post(
            row_index=1,
            keyword="AD란",
            category="IT",
            status=PostStatus.PENDING,
            content=PostContent(title="AD란", body_markdown="## AD\n본문"),
        )
        # row_index=1인 발행완료 글 (자기 자신과 같은 row)
        pub_self = self._make_published_post(1, "AD란", "IT", "https://test.tistory.com/1")
        pub_other = self._make_published_post(2, "SSO란", "IT", "https://test.tistory.com/2")

        repo = InMemoryPostRepository([pending, pub_self, pub_other])
        browser = MockBrowserAdapter(publish_url="https://test.tistory.com/99")
        use_case = PublishPostsUseCase(repo=repo, browser=browser)

        use_case.execute()

        saved = repo.all()[0]
        assert "관련 글" in saved.content.body_markdown
        assert "SSO란" in saved.content.body_markdown
        # 자기 자신(AD란)은 관련 글 링크에 포함되지 않아야 함
        assert 'href="https://test.tistory.com/1"' not in saved.content.body_markdown
