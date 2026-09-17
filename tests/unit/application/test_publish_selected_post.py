"""PublishSelectedPostUseCase — 관리자가 선택한 게시물 1건 수동 발행."""
from __future__ import annotations

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.application.use_cases.publish_selected_post import (
    ManualPublishOutcome,
    PublishSelectedPostUseCase,
)
from src.domain.entities.post import Post
from src.domain.ports.pipeline_lock_port import PipelineLockPort
from src.domain.services.internal_link_service import InternalLinkService
from src.domain.services.quota_manager import QuotaManager
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.browser.mock_browser import MockBrowserAdapter
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


class FakeLock(PipelineLockPort):
    def __init__(self, available: bool = True):
        self._available = available
        self.acquired = False
        self.released = False

    def acquire(self) -> bool:
        self.acquired = self._available
        return self._available

    def release(self) -> None:
        self.released = True


class ExplodingBrowser(MockBrowserAdapter):
    def publish(self, post: Post):
        raise RuntimeError("chromedriver crashed")


def _post(row: int = 2, keyword: str = "OpenTelemetry 구축", **kwargs) -> Post:
    defaults = dict(
        status=PostStatus.PENDING,
        content=PostContent(title="제목", body_markdown="## 본문\n" + "x" * 3000),
        quality_score=85,
    )
    defaults.update(kwargs)
    return Post(row_index=row, keyword=keyword, **defaults)


def _use_case(repo, browser=None, lock=None, daily_limit=15):
    return PublishSelectedPostUseCase(
        repo=repo,
        browser=browser or MockBrowserAdapter(publish_url="https://blog.tistory.com/10"),
        enricher=InternalLinkEnricher(InternalLinkService()),
        quota=QuotaManager(daily_limit=daily_limit),
        lock=lock or FakeLock(),
    )


class TestManualPublishSuccess:
    def test_선택한_게시물만_발행하고_URL_기록(self):
        target, other = _post(2, "OpenTelemetry 구축"), _post(3, "Istio vs Linkerd 비교")
        repo = InMemoryPostRepository([target, other])
        browser = MockBrowserAdapter(publish_url="https://blog.tistory.com/10")

        result = _use_case(repo, browser).execute(row_index=2)

        assert result.outcome == ManualPublishOutcome.PUBLISHED
        assert result.url == "https://blog.tistory.com/10"
        assert [p.row_index for p in browser.published_posts] == [2]
        assert target.status == PostStatus.PUBLISHED
        assert other.status == PostStatus.PENDING

    def test_브라우저와_락을_항상_정리(self):
        repo = InMemoryPostRepository([_post()])
        browser, lock = MockBrowserAdapter(), FakeLock()
        _use_case(repo, browser, lock).execute(row_index=2)
        assert browser.stopped is True
        assert lock.released is True


class TestManualPublishRejected:
    def test_없는_행이면_거부(self):
        result = _use_case(InMemoryPostRepository([_post(2)])).execute(row_index=99)
        assert result.outcome == ManualPublishOutcome.REJECTED
        assert "찾을 수 없" in result.message

    def test_발행대기가_아니면_거부(self):
        post = _post(status=PostStatus.PUBLISHED, published_url="https://x/1")
        result = _use_case(InMemoryPostRepository([post])).execute(row_index=2)
        assert result.outcome == ManualPublishOutcome.REJECTED
        assert "발행대기" in result.message

    def test_본문이_짧으면_사유와_함께_거부(self):
        post = _post(content=PostContent(title="t", body_markdown="짧은 본문"))
        result = _use_case(InMemoryPostRepository([post])).execute(row_index=2)
        assert result.outcome == ManualPublishOutcome.REJECTED
        assert "3000" in result.message

    def test_품질점수가_낮으면_거부(self):
        post = _post(quality_score=50)
        result = _use_case(InMemoryPostRepository([post])).execute(row_index=2)
        assert result.outcome == ManualPublishOutcome.REJECTED
        assert "품질" in result.message

    def test_이미_발행된_키워드와_중복이면_상태_변경_없이_거부(self):
        published = _post(
            5, "OpenTelemetry 분산 추적 구축", status=PostStatus.PUBLISHED,
            published_url="https://x/5",
        )
        target = _post(2, "OpenTelemetry 분산 추적 구축 가이드")
        repo = InMemoryPostRepository([published, target])
        browser = MockBrowserAdapter()

        result = _use_case(repo, browser).execute(row_index=2)

        assert result.outcome == ManualPublishOutcome.REJECTED
        assert "중복" in result.message
        assert target.status == PostStatus.PENDING
        assert browser.started is False

    def test_일일_쿼터_소진이면_거부(self):
        result = _use_case(InMemoryPostRepository([_post()]), daily_limit=0).execute(row_index=2)
        assert result.outcome == ManualPublishOutcome.REJECTED
        assert "쿼터" in result.message

    def test_자동_파이프라인_실행중이면_브라우저_열지_않고_거부(self):
        post = _post()
        browser, lock = MockBrowserAdapter(), FakeLock(available=False)
        result = _use_case(InMemoryPostRepository([post]), browser, lock).execute(row_index=2)
        assert result.outcome == ManualPublishOutcome.REJECTED
        assert "실행 중" in result.message
        assert browser.started is False
        assert lock.released is False
        assert post.status == PostStatus.PENDING


class TestManualPublishFailure:
    def test_로그인_실패면_발행대기_유지(self):
        post = _post()
        browser = MockBrowserAdapter(login_success=False)
        result = _use_case(InMemoryPostRepository([post]), browser).execute(row_index=2)
        assert result.outcome == ManualPublishOutcome.FAILED
        assert "로그인" in result.message
        assert post.status == PostStatus.PENDING
        assert browser.stopped is True

    def test_발행_실패면_발행실패로_기록(self):
        post = _post()
        browser = MockBrowserAdapter(publish_error="Tistory 500")
        result = _use_case(InMemoryPostRepository([post]), browser).execute(row_index=2)
        assert result.outcome == ManualPublishOutcome.FAILED
        assert post.status == PostStatus.FAILED
        assert "Tistory 500" in result.message

    def test_발행_중_예외면_발행실패로_기록하고_정리(self):
        post, lock = _post(), FakeLock()
        browser = ExplodingBrowser()
        result = _use_case(InMemoryPostRepository([post]), browser, lock).execute(row_index=2)
        assert result.outcome == ManualPublishOutcome.FAILED
        assert post.status == PostStatus.FAILED
        assert browser.stopped is True
        assert lock.released is True
