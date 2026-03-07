"""Unit tests for ResetStuckPostsUseCase — TDD RED phase."""
from datetime import datetime, timedelta

from src.application.use_cases.reset_stuck_posts import ResetStuckPostsUseCase
from src.domain.entities.post import Post
from src.domain.services.retry_policy import RetryPolicy
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


class TestResetStuckPosts:
    """고스트 포스트 복구 테스트."""

    def test_고스트_1건_복구(self):
        stuck = Post(
            row_index=1,
            keyword="AD란",
            status=PostStatus.PUBLISHING,
            content=PostContent(title="제목", body_markdown="내용"),
        )
        repo = InMemoryPostRepository([stuck])
        use_case = ResetStuckPostsUseCase(repo=repo)

        count = use_case.execute()

        assert count == 1
        recovered = repo.all()[0]
        assert recovered.status == PostStatus.PENDING
        assert "자동 복구" in recovered.error_message

    def test_고스트_여러건_복구(self):
        posts = [
            Post(row_index=1, keyword="AD란", status=PostStatus.PUBLISHING,
                 content=PostContent(title="제목1", body_markdown="내용1")),
            Post(row_index=2, keyword="SSO란", status=PostStatus.PUBLISHING,
                 content=PostContent(title="제목2", body_markdown="내용2")),
            Post(row_index=3, keyword="SAML이란", status=PostStatus.PENDING,
                 content=PostContent(title="제목3", body_markdown="내용3")),
        ]
        repo = InMemoryPostRepository(posts)
        use_case = ResetStuckPostsUseCase(repo=repo)

        count = use_case.execute()

        assert count == 2
        assert repo.all()[0].status == PostStatus.PENDING
        assert repo.all()[1].status == PostStatus.PENDING
        assert repo.all()[2].status == PostStatus.PENDING  # 원래 PENDING

    def test_빈_목록_처리(self):
        repo = InMemoryPostRepository([])
        use_case = ResetStuckPostsUseCase(repo=repo)

        count = use_case.execute()

        assert count == 0

    def test_stuck_없으면_0_반환(self):
        post = Post(
            row_index=1,
            keyword="AD란",
            status=PostStatus.PUBLISHED,
            content=PostContent(title="제목", body_markdown="내용"),
        )
        repo = InMemoryPostRepository([post])
        use_case = ResetStuckPostsUseCase(repo=repo)

        count = use_case.execute()

        assert count == 0
        assert repo.all()[0].status == PostStatus.PUBLISHED


class TestRetryFailed:
    """실패 포스트 재시도 테스트."""

    def test_retry_failed_옵트인_동작(self):
        """retry_failed=True 시 FAILED→PENDING 전이 + retry_count 증가."""
        failed_post = Post(
            row_index=12,
            keyword="Jenkins vs GitHub Actions",
            status=PostStatus.FAILED,
            error_message="이전 UI 버튼 코드 실패",
            content=PostContent(title="제목", body_markdown="내용"),
        )
        repo = InMemoryPostRepository([failed_post])
        use_case = ResetStuckPostsUseCase(repo=repo, retry_failed=True)

        count = use_case.execute()

        assert count == 1
        recovered = repo.all()[0]
        assert recovered.status == PostStatus.PENDING
        assert recovered.error_message == ""
        assert recovered.retry_count == 1
        assert recovered.next_retry_at is not None

    def test_retry_failed_기본_비활성(self):
        """기본값(retry_failed=False) 시 FAILED 포스트 무시."""
        failed_post = Post(
            row_index=12,
            keyword="Jenkins vs GitHub Actions",
            status=PostStatus.FAILED,
            error_message="이전 UI 버튼 코드 실패",
            content=PostContent(title="제목", body_markdown="내용"),
        )
        repo = InMemoryPostRepository([failed_post])
        use_case = ResetStuckPostsUseCase(repo=repo)  # retry_failed 기본값 False

        count = use_case.execute()

        assert count == 0
        assert repo.all()[0].status == PostStatus.FAILED  # 그대로

    def test_retry_최대횟수_초과_건너뜀(self):
        """retry_count >= max_retries → 재시도 건너뜀."""
        failed_post = Post(
            row_index=12,
            keyword="초과",
            status=PostStatus.FAILED,
            error_message="실패",
            content=PostContent(title="제목", body_markdown="내용"),
            retry_count=3,
        )
        repo = InMemoryPostRepository([failed_post])
        policy = RetryPolicy(max_retries=3)
        use_case = ResetStuckPostsUseCase(
            repo=repo, retry_failed=True, retry_policy=policy,
        )

        count = use_case.execute()

        assert count == 0
        assert repo.all()[0].status == PostStatus.FAILED

    def test_retry_시간_미도래_건너뜀(self):
        """next_retry_at이 미래 → 건너뜀."""
        failed_post = Post(
            row_index=12,
            keyword="이르다",
            status=PostStatus.FAILED,
            error_message="실패",
            content=PostContent(title="제목", body_markdown="내용"),
            retry_count=1,
            next_retry_at=datetime.now() + timedelta(hours=5),
        )
        repo = InMemoryPostRepository([failed_post])
        use_case = ResetStuckPostsUseCase(repo=repo, retry_failed=True)

        count = use_case.execute()

        assert count == 0
        assert repo.all()[0].status == PostStatus.FAILED


class TestResetRevisingStuck:
    """수정중 고스트 포스트 복구 테스트."""

    def test_수정중_1건_복구(self):
        stuck = Post(
            row_index=1,
            keyword="AD란",
            status=PostStatus.REVISING,
            content=PostContent(title="제목", body_markdown="내용"),
            entry_id="100",
        )
        repo = InMemoryPostRepository([stuck])
        use_case = ResetStuckPostsUseCase(repo=repo)

        count = use_case.execute()

        assert count == 1
        recovered = repo.all()[0]
        assert recovered.status == PostStatus.REVISION_PENDING
        assert "자동 복구" in recovered.error_message

    def test_수정중_여러건_복구(self):
        posts = [
            Post(row_index=1, keyword="AD란", status=PostStatus.REVISING,
                 content=PostContent(title="제목1", body_markdown="내용1"),
                 entry_id="100"),
            Post(row_index=2, keyword="SSO란", status=PostStatus.REVISING,
                 content=PostContent(title="제목2", body_markdown="내용2"),
                 entry_id="101"),
            Post(row_index=3, keyword="SAML이란", status=PostStatus.REVISION_PENDING,
                 content=PostContent(title="제목3", body_markdown="내용3"),
                 entry_id="102"),
        ]
        repo = InMemoryPostRepository(posts)
        use_case = ResetStuckPostsUseCase(repo=repo)

        count = use_case.execute()

        assert count == 2
        assert repo.all()[0].status == PostStatus.REVISION_PENDING
        assert repo.all()[1].status == PostStatus.REVISION_PENDING
        assert repo.all()[2].status == PostStatus.REVISION_PENDING  # 원래 그대로

    def test_publishing_and_revising_동시_복구(self):
        posts = [
            Post(row_index=1, keyword="발행중", status=PostStatus.PUBLISHING,
                 content=PostContent(title="제목", body_markdown="내용")),
            Post(row_index=2, keyword="수정중", status=PostStatus.REVISING,
                 content=PostContent(title="제목", body_markdown="내용"),
                 entry_id="200"),
        ]
        repo = InMemoryPostRepository(posts)
        use_case = ResetStuckPostsUseCase(repo=repo)

        count = use_case.execute()

        assert count == 2
        assert repo.all()[0].status == PostStatus.PENDING
        assert repo.all()[1].status == PostStatus.REVISION_PENDING
