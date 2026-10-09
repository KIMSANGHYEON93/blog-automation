"""수정 이력·재시도 한도·편집 후 재검증 — 유스케이스 경로 회귀 테스트."""
from __future__ import annotations

from datetime import datetime

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.application.use_cases.batch_recover import BatchRecoverUseCase
from src.application.use_cases.edit_post import EditPostUseCase
from src.application.use_cases.publish_selected_post import (
    ManualPublishOutcome,
    PublishSelectedPostUseCase,
)
from src.application.use_cases.revise_posts import RevisePostsUseCase
from src.application.use_cases.revise_selected_post import ReviseSelectedPostUseCase
from src.domain.entities.post import Post
from src.domain.ports.pipeline_lock_port import PipelineLockPort
from src.domain.services.internal_link_service import InternalLinkService
from src.domain.services.quota_manager import QuotaManager
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.browser.mock_browser import MockBrowserAdapter
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository

BODY = "## 본문\n" + "가" * 3000


class OpenLock(PipelineLockPort):
    def acquire(self) -> bool:
        return True

    def release(self) -> None:
        pass


def _revision_pending(row: int = 2) -> Post:
    return Post(row_index=row, keyword=f"글 {row}", status=PostStatus.REVISION_PENDING,
                content=PostContent(title="t", body_markdown=BODY), entry_id=str(row),
                published_url=f"https://t/{row}", published_at=datetime(2026, 9, 1, 9, 0))


class TestRevisionHistory:
    def test_자동_수정은_최초_발행일을_지키고_수정_이력을_남긴다(self):
        repo = InMemoryPostRepository([_revision_pending()])

        RevisePostsUseCase(repo=repo, browser=MockBrowserAdapter(),
                           enricher=InternalLinkEnricher(InternalLinkService())).execute()

        post = repo.all()[0]
        assert post.status == PostStatus.PUBLISHED
        assert post.published_at == datetime(2026, 9, 1, 9, 0)
        assert post.revision_count == 1 and post.revised_at is not None
        assert repo.count_published_today() == 0  # 수정은 일일 발행 한도를 쓰지 않는다

    def test_수동_수정도_같은_이력_규칙(self):
        repo = InMemoryPostRepository([_revision_pending()])

        ReviseSelectedPostUseCase(repo=repo, browser=MockBrowserAdapter(),
                                  lock=OpenLock()).execute(2)

        post = repo.all()[0]
        assert post.published_at == datetime(2026, 9, 1, 9, 0)
        assert post.revision_count == 1 and post.revised_at is not None


class TestRetryLimitOnRecover:
    def test_recover_failed도_최대_재시도를_넘기지_않는다(self):
        post = Post(row_index=2, keyword="k", status=PostStatus.FAILED,
                    error_message="Connection timed out", retry_count=3)
        repo = InMemoryPostRepository([post])

        result = BatchRecoverUseCase(repo=repo).execute()

        assert result.recovered == 0
        assert repo.all()[0].status == PostStatus.FAILED

    def test_recover_failed로_복구하면_재시도_횟수가_는다(self):
        post = Post(row_index=2, keyword="k", status=PostStatus.FAILED,
                    error_message="Connection timed out")
        repo = InMemoryPostRepository([post])

        BatchRecoverUseCase(repo=repo).execute()

        assert repo.all()[0].retry_count == 1
        assert repo.all()[0].next_retry_at is not None


def _publisher(repo):
    return PublishSelectedPostUseCase(
        repo=repo, browser=MockBrowserAdapter(),
        enricher=InternalLinkEnricher(InternalLinkService()),
        quota=QuotaManager(), lock=OpenLock(),
    )


class TestEditInvalidatesVerification:
    def _repo(self) -> InMemoryPostRepository:
        return InMemoryPostRepository([Post(
            row_index=2, keyword="OAuth 개념", status=PostStatus.PENDING, quality_score=85,
            content=PostContent(title="t", body_markdown=BODY + "\n\n[[직접 해 보니]]"),
        )])

    def test_편집_뒤에는_이전_점수로_발행할_수_없다(self):
        repo = self._repo()
        EditPostUseCase(repo).edit(2, title="t", body=BODY + "\n\n실제로 해 봤더니 ...",
                                   tags="", category="")

        result = _publisher(repo).execute(2)

        assert result.outcome == ManualPublishOutcome.REJECTED
        assert "재검증" in result.message

    def test_관리자가_명시적으로_승인하면_발행된다(self):
        repo = self._repo()
        editor = EditPostUseCase(repo)
        editor.edit(2, title="t", body=BODY + "\n\n실제로 해 봤더니 ...", tags="", category="")
        editor.approve(2)

        assert _publisher(repo).execute(2).outcome == ManualPublishOutcome.PUBLISHED

    def test_내용_그대로_저장이나_사진_추가는_재검증을_요구하지_않는다(self):
        repo = InMemoryPostRepository([Post(
            row_index=2, keyword="OAuth 개념", status=PostStatus.PENDING, quality_score=85,
            content=PostContent(title="t", body_markdown=BODY),
        )])
        editor = EditPostUseCase(repo)
        editor.edit(2, title="새 제목", body=BODY.replace("\n", "\r\n"), tags="", category="")
        editor.add_photo(2, "a1.jpg")

        assert repo.all()[0].publish_blockers() == []
