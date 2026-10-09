"""수동 발행·수정 발행 — 잠금을 잡은 뒤 최신 상태로 다시 판단한다."""
from __future__ import annotations

from datetime import datetime

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.application.use_cases.publish_selected_post import (
    ManualPublishOutcome,
    PublishSelectedPostUseCase,
)
from src.application.use_cases.revise_selected_post import ReviseSelectedPostUseCase
from src.domain.entities.post import PUBLISH_UNCONFIRMED, Post
from src.domain.ports.pipeline_lock_port import PipelineLockPort
from src.domain.services.internal_link_service import InternalLinkService
from src.domain.services.quota_manager import QuotaManager
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.browser.mock_browser import MockBrowserAdapter
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


class RacingLock(PipelineLockPort):
    """잠금을 기다리는 사이 다른 실행이 시트를 바꾼 상황."""

    def __init__(self, on_acquire):
        self._on_acquire = on_acquire
        self.released = False

    def acquire(self) -> bool:
        self._on_acquire()
        return True

    def release(self) -> None:
        self.released = True


def _post(row: int = 2, keyword: str = "OAuth 개념", **kwargs) -> Post:
    defaults = dict(
        status=PostStatus.PENDING,
        content=PostContent(title="제목", body_markdown="## 본문\n" + "x" * 3000),
        quality_score=85,
    )
    defaults.update(kwargs)
    return Post(row_index=row, keyword=keyword, **defaults)


def _publisher(repo, browser, lock, daily_limit=15):
    return PublishSelectedPostUseCase(
        repo=repo, browser=browser,
        enricher=InternalLinkEnricher(InternalLinkService()),
        quota=QuotaManager(daily_limit=daily_limit), lock=lock,
    )


def test_잠금_대기_중_다른_실행이_발행했으면_발행하지_않는다():
    post = _post()
    repo = InMemoryPostRepository([post])

    def other_run_published():
        repo.save(_post(status=PostStatus.PUBLISHED, published_url="https://t/1",
                        published_at=datetime.now()))

    browser = MockBrowserAdapter()
    result = _publisher(repo, browser, RacingLock(other_run_published)).execute(2)

    assert result.outcome == ManualPublishOutcome.REJECTED
    assert browser.published_posts == []


def test_잠금_대기_중_한도가_찼으면_발행하지_않는다():
    repo = InMemoryPostRepository([_post()])

    def other_run_used_quota():
        repo.save(_post(row=9, keyword="다른 글", status=PostStatus.PUBLISHED,
                        published_at=datetime.now()))

    browser = MockBrowserAdapter()
    result = _publisher(repo, browser, RacingLock(other_run_used_quota), daily_limit=1).execute(2)

    assert result.outcome == ManualPublishOutcome.REJECTED
    assert browser.published_posts == []


def test_잠금_대기_중_같은_키워드가_발행되면_중복으로_거부():
    repo = InMemoryPostRepository([_post()])

    def other_run_same_keyword():
        repo.save(_post(row=9, status=PostStatus.PUBLISHED, published_url="https://t/9"))

    browser = MockBrowserAdapter()
    result = _publisher(repo, browser, RacingLock(other_run_same_keyword)).execute(2)

    assert result.outcome == ManualPublishOutcome.REJECTED
    assert "OAuth 개념" in result.message
    assert browser.published_posts == []


def test_결과_불명_글과_같은_키워드는_수동으로도_거부():
    unknown = _post(row=9, status=PostStatus.FAILED, error_message=f"{PUBLISH_UNCONFIRMED}: x")
    repo = InMemoryPostRepository([unknown, _post()])
    browser = MockBrowserAdapter()

    result = _publisher(repo, browser, RacingLock(lambda: None)).execute(2)

    assert result.outcome == ManualPublishOutcome.REJECTED
    assert browser.published_posts == []


class ExplodingBrowser(MockBrowserAdapter):
    def publish(self, post: Post):
        raise RuntimeError("chromedriver crashed")


def test_수동_발행_중_예외는_결과_불명으로_남긴다():
    repo = InMemoryPostRepository([_post()])

    result = _publisher(repo, ExplodingBrowser(), RacingLock(lambda: None)).execute(2)

    assert result.outcome == ManualPublishOutcome.FAILED
    assert PUBLISH_UNCONFIRMED in repo.all()[0].error_message


def test_플랫폼_한도_응답이면_발행대기_유지():
    repo = InMemoryPostRepository([_post()])
    browser = MockBrowserAdapter(publish_error="공개 발행할 수 있는 글은 최대 15개까지입니다.")

    result = _publisher(repo, browser, RacingLock(lambda: None)).execute(2)

    assert result.outcome == ManualPublishOutcome.FAILED
    assert repo.all()[0].status == PostStatus.PENDING


def test_수정_발행도_잠금_뒤_최신_상태로_판단():
    published = _post(status=PostStatus.REVISION_PENDING, entry_id="10",
                      published_url="https://t/10")
    repo = InMemoryPostRepository([published])

    def other_run_revised():
        repo.save(_post(status=PostStatus.PUBLISHED, entry_id="10", published_url="https://t/10"))

    browser = MockBrowserAdapter()
    result = ReviseSelectedPostUseCase(
        repo=repo, browser=browser, lock=RacingLock(other_run_revised),
    ).execute(2)

    assert result.outcome == ManualPublishOutcome.REJECTED
    assert browser.updated_posts == []
