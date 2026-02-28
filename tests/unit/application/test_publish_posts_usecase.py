"""Unit tests for PublishPostsUseCase — TDD RED phase."""

from src.application.use_cases.publish_posts import PublishPostsUseCase
from src.domain.entities.post import Post
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
