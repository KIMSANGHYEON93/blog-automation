"""Unit tests for BatchRecoverUseCase."""
from src.application.use_cases.batch_recover import BatchRecoverUseCase
from src.domain.entities.post import Post
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


def _make_failed_post(row_index: int, keyword: str, error: str) -> Post:
    return Post(
        row_index=row_index,
        keyword=keyword,
        status=PostStatus.FAILED,
        content=PostContent(title=keyword, body_markdown="본문"),
        error_message=error,
    )


class TestBatchRecoverNormal:
    """정상 일괄 복구 흐름."""

    def test_quota_exceeded_자동_복구(self):
        post = _make_failed_post(1, "AD란", "최대 15개까지 발행 가능합니다")
        repo = InMemoryPostRepository([post])
        uc = BatchRecoverUseCase(repo=repo)

        result = uc.execute()

        assert result.recovered == 1
        assert result.total_failed == 1
        assert repo.all()[0].status == PostStatus.PENDING

    def test_timeout_자동_복구(self):
        post = _make_failed_post(1, "SSO란", "Connection timed out")
        repo = InMemoryPostRepository([post])
        uc = BatchRecoverUseCase(repo=repo)

        result = uc.execute()

        assert result.recovered == 1
        assert repo.all()[0].status == PostStatus.PENDING

    def test_auth_failure_수동_건너뜀(self):
        post = _make_failed_post(1, "LDAP란", "로그인 실패")
        repo = InMemoryPostRepository([post])
        uc = BatchRecoverUseCase(repo=repo)

        result = uc.execute()

        assert result.recovered == 0
        assert result.skipped_manual == 1
        assert repo.all()[0].status == PostStatus.FAILED

    def test_validation_수정대기_건너뜀(self):
        post = _make_failed_post(1, "K8s란", "HTML 검증 실패")
        repo = InMemoryPostRepository([post])
        uc = BatchRecoverUseCase(repo=repo)

        result = uc.execute()

        assert result.recovered == 0
        assert result.skipped_revision == 1

    def test_혼합_에러_복구(self):
        posts = [
            _make_failed_post(1, "AD란", "최대 15개까지"),   # quota → 자동 복구
            _make_failed_post(2, "SSO란", "로그인 실패"),     # auth → 수동
            _make_failed_post(3, "K8s란", "timeout"),        # timeout → 자동 복구
            _make_failed_post(4, "Docker란", "알 수 없는 오류"),  # unknown → 수동
        ]
        repo = InMemoryPostRepository(posts)
        uc = BatchRecoverUseCase(repo=repo)

        result = uc.execute()

        assert result.total_failed == 4
        assert result.recovered == 2
        assert result.skipped_manual == 2
        assert repo.all()[0].status == PostStatus.PENDING
        assert repo.all()[1].status == PostStatus.FAILED
        assert repo.all()[2].status == PostStatus.PENDING
        assert repo.all()[3].status == PostStatus.FAILED

    def test_실패_포스트_없음(self):
        repo = InMemoryPostRepository([])
        uc = BatchRecoverUseCase(repo=repo)

        result = uc.execute()

        assert result.total_failed == 0
        assert result.recovered == 0
