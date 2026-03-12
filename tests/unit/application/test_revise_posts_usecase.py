"""Unit tests for RevisePostsUseCase — TDD RED phase."""

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.application.use_cases.revise_posts import RevisePostsUseCase
from src.domain.entities.post import Post
from src.domain.exceptions import DailyPublishLimitError
from src.domain.services.internal_link_service import InternalLinkService
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.browser.mock_browser import MockBrowserAdapter
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


def make_revisable_post(row_index: int = 1, keyword: str = "AD란",
                        entry_id: str = "100"):
    return Post(
        row_index=row_index,
        keyword=keyword,
        status=PostStatus.REVISION_PENDING,
        content=PostContent(title="테스트 제목", body_markdown="## 수정된 내용\n본문"),
        entry_id=entry_id,
    )


def make_use_case(repo, browser, max_posts=5):
    """Factory for RevisePostsUseCase with fully-injected dependencies."""
    enricher = InternalLinkEnricher(InternalLinkService())
    return RevisePostsUseCase(
        repo=repo, browser=browser,
        enricher=enricher,
        max_posts=max_posts,
    )


class TestRevisePostsNormalFlow:
    """정상 수정 흐름 테스트."""

    def test_2건_정상_수정(self):
        posts = [
            make_revisable_post(1, "AD란", "100"),
            make_revisable_post(2, "SSO란", "101"),
        ]
        repo = InMemoryPostRepository(posts)
        browser = MockBrowserAdapter(
            login_success=True, update_url="https://test.tistory.com/100"
        )
        use_case = make_use_case(repo, browser)

        stats = use_case.execute()

        assert stats.revised == 2
        assert stats.failed == 0
        assert browser.stopped is True

    def test_수정_후_상태_PUBLISHED(self):
        post = make_revisable_post(1, entry_id="100")
        repo = InMemoryPostRepository([post])
        browser = MockBrowserAdapter(update_url="https://test.tistory.com/100")
        use_case = make_use_case(repo, browser)

        use_case.execute()

        saved = repo.all()[0]
        assert saved.status == PostStatus.PUBLISHED
        assert saved.published_url == "https://test.tistory.com/100"


class TestRevisePostsSkip:
    """수정 불가 포스트 건너뛰기."""

    def test_entry_id_없는_포스트_건너뛰기(self):
        post = Post(
            row_index=1,
            keyword="AD란",
            status=PostStatus.REVISION_PENDING,
            content=PostContent(title="제목", body_markdown="본문 있음"),
            entry_id="",  # entry_id 없음
        )
        repo = InMemoryPostRepository([post])
        browser = MockBrowserAdapter()
        use_case = make_use_case(repo, browser)

        stats = use_case.execute()

        assert stats.skipped == 1
        assert stats.revised == 0

    def test_본문_없는_포스트_건너뛰기(self):
        post = Post(
            row_index=1,
            keyword="AD란",
            status=PostStatus.REVISION_PENDING,
            content=PostContent(title="제목", body_markdown=""),
            entry_id="100",
        )
        repo = InMemoryPostRepository([post])
        browser = MockBrowserAdapter()
        use_case = make_use_case(repo, browser)

        stats = use_case.execute()

        assert stats.skipped == 1

    def test_content_None_건너뛰기(self):
        post = Post(row_index=1, keyword="AD란",
                    status=PostStatus.REVISION_PENDING, entry_id="100")
        repo = InMemoryPostRepository([post])
        browser = MockBrowserAdapter()
        use_case = make_use_case(repo, browser)

        stats = use_case.execute()

        assert stats.skipped == 1


class TestRevisePostsFailure:
    """수정 실패 처리."""

    def test_수정_실패_시_FAILED_상태(self):
        post = make_revisable_post()
        repo = InMemoryPostRepository([post])
        browser = MockBrowserAdapter(update_error="에디터 로딩 실패")
        use_case = make_use_case(repo, browser)

        stats = use_case.execute()

        assert stats.failed == 1
        saved = repo.all()[0]
        assert saved.status == PostStatus.FAILED
        assert "에디터 로딩 실패" in saved.error_message

    def test_로그인_실패_즉시_중단(self):
        posts = [make_revisable_post(1, entry_id="100"),
                 make_revisable_post(2, entry_id="101")]
        repo = InMemoryPostRepository(posts)
        browser = MockBrowserAdapter(login_success=False)
        use_case = make_use_case(repo, browser)

        stats = use_case.execute()

        assert stats.revised == 0
        assert len(browser.updated_posts) == 0
        assert browser.stopped is True


class TestRevisePostsBrowserLifecycle:
    """브라우저 생명주기 관리."""

    def test_예외_발생_시_브라우저_종료(self):
        class BuggyBrowser(MockBrowserAdapter):
            def update(self, post):
                raise RuntimeError("예상치 못한 오류")

        post = make_revisable_post()
        repo = InMemoryPostRepository([post])
        browser = BuggyBrowser()
        use_case = make_use_case(repo, browser)

        use_case.execute()

        assert browser.stopped is True

    def test_빈_목록일_때_브라우저_미시작(self):
        repo = InMemoryPostRepository([])
        browser = MockBrowserAdapter()
        use_case = make_use_case(repo, browser)

        stats = use_case.execute()

        assert stats.revised == 0
        assert stats.skipped == 0
        assert browser.started is False


class TestRevisePostsDailyLimit:
    """일일 발행 제한 처리."""

    def test_일일_제한_시_나머지_건너뛰기(self):
        class DailyLimitBrowser(MockBrowserAdapter):
            call_count = 0

            def update(self, post):
                self.call_count += 1
                if self.call_count >= 2:
                    raise DailyPublishLimitError("최대 15개까지")
                return super().update(post)

        posts = [make_revisable_post(i, f"kw{i}", str(100 + i)) for i in range(1, 4)]
        repo = InMemoryPostRepository(posts)
        browser = DailyLimitBrowser(update_url="https://test.tistory.com/100")
        use_case = make_use_case(repo, browser, max_posts=5)

        stats = use_case.execute()

        assert stats.revised == 1
        assert stats.failed == 0
        # 2번째 글은 REVISION_PENDING으로 복원 (일일 제한)
        assert repo.all()[1].status == PostStatus.REVISION_PENDING
        # 3번째 글은 시도조차 안 함
        assert repo.all()[2].status == PostStatus.REVISION_PENDING
        assert browser.stopped is True

    def test_일일_제한_포스트_수정대기_복원(self):
        class ImmediateLimitBrowser(MockBrowserAdapter):
            def update(self, post):
                raise DailyPublishLimitError("최대 15개까지")

        post = make_revisable_post()
        repo = InMemoryPostRepository([post])
        browser = ImmediateLimitBrowser()
        use_case = make_use_case(repo, browser)

        stats = use_case.execute()

        assert stats.revised == 0
        assert stats.failed == 0
        saved = repo.all()[0]
        assert saved.status == PostStatus.REVISION_PENDING
