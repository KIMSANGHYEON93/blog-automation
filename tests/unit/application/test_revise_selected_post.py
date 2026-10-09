"""ReviseSelectedPostUseCase — 발행된 글 1건을 같은 URL에서 고쳐 쓴다(대시보드 '수정 발행')."""
from __future__ import annotations

from datetime import datetime

from src.application.use_cases.publish_selected_post import ManualPublishOutcome
from src.application.use_cases.revise_selected_post import ReviseSelectedPostUseCase
from src.domain.entities.post import Post
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.domain.value_objects.publish_result import PublishResult
from src.infrastructure.browser.mock_browser import MockBrowserAdapter
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository
from tests.unit.application.test_publish_selected_post import FakeLock

URL = "https://blog.naver.com/myblog/224421344442"
FIRST_PUBLISHED = datetime(2026, 9, 23, 23, 3)


def _post(status=PostStatus.REVISION_PENDING, entry_id="224421344442") -> Post:
    return Post(
        row_index=4, keyword="MCP란", status=status,
        content=PostContent(title="MCP란?", body_markdown="본문" * 2000, tags="MCP"),
        published_url=URL, published_at=FIRST_PUBLISHED, entry_id=entry_id,
        quality_score=90,
    )


def _run(post: Post, browser=None, lock=None):
    repo = InMemoryPostRepository([post])
    browser = browser or MockBrowserAdapter(update_url=URL)
    lock = lock or FakeLock()
    result = ReviseSelectedPostUseCase(repo, browser, lock).execute(post.row_index)
    return result, repo.find_all()[0], browser, lock


def test_수정하면_같은_URL로_발행완료_첫_발행일은_그대로():
    result, post, browser, lock = _run(_post())
    assert result.outcome == ManualPublishOutcome.REVISED
    assert post.status == PostStatus.PUBLISHED
    assert post.published_url == URL
    # 수정을 오늘 발행으로 세면 하루 1건 한도를 먹는다
    assert post.published_at == FIRST_PUBLISHED
    assert browser.updated_posts and lock.released


def test_수정대기가_아니면_거부하고_브라우저를_열지_않는다():
    result, post, browser, lock = _run(_post(status=PostStatus.PUBLISHED))
    assert result.outcome == ManualPublishOutcome.REJECTED
    assert post.status == PostStatus.PUBLISHED
    # 판단은 잠금을 잡은 뒤 최신 상태로 한다 — 잠금은 잡았다 풀고, 브라우저는 열지 않는다
    assert not browser.updated_posts and not browser.started and lock.released


def test_글_번호가_없으면_거부():
    result, _, browser, _ = _run(_post(entry_id=""))
    assert result.outcome == ManualPublishOutcome.REJECTED
    assert not browser.updated_posts


def test_다른_작업이_락을_쥐고_있으면_거부():
    result, post, browser, _ = _run(_post(), lock=FakeLock(available=False))
    assert result.outcome == ManualPublishOutcome.REJECTED
    assert post.status == PostStatus.REVISION_PENDING
    assert not browser.updated_posts


def test_실패하면_수정대기로_돌아가_다시_시도할_수_있다():
    # 수정은 같은 글을 덮어써서 중복이 생기지 않는다 — 실패 상태로 빼지 않고 사유만 남긴다
    browser = MockBrowserAdapter(update_error="본문 붙여넣기가 반영되지 않음")
    result, post, _, lock = _run(_post(), browser=browser)
    assert result.outcome == ManualPublishOutcome.FAILED
    assert post.status == PostStatus.REVISION_PENDING
    assert "본문 붙여넣기" in post.error_message
    assert lock.released


def test_예외가_나도_수정대기로_돌아간다():
    class Exploding(MockBrowserAdapter):
        def update(self, post):
            raise RuntimeError("chromedriver crashed")

    result, post, _, _ = _run(_post(), browser=Exploding())
    assert result.outcome == ManualPublishOutcome.FAILED
    assert post.status == PostStatus.REVISION_PENDING
    assert "chromedriver" in post.error_message


def test_점검_경고는_오류_열에_남긴다():
    class Warned(MockBrowserAdapter):
        def update(self, post):
            return PublishResult.ok(URL, warnings=("태그 1개",))

    result, post, _, _ = _run(_post(), browser=Warned())
    assert post.status == PostStatus.PUBLISHED
    assert "태그 1개" in post.error_message and "태그 1개" in result.message
