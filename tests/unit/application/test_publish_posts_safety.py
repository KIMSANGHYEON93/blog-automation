"""자동 발행 안전 규칙 — 일일 한도·동일 배치 중복·앞쪽 불량 글·결과 불명 처리 회귀 테스트."""
from __future__ import annotations

from datetime import datetime

import pytest

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.application.use_cases.publish_posts import PublishPostsUseCase
from src.application.use_cases.reset_stuck_posts import ResetStuckPostsUseCase
from src.domain.entities.post import PUBLISH_UNCONFIRMED, Post
from src.domain.services.internal_link_service import InternalLinkService
from src.domain.services.publish_policy import PublishPolicy
from src.domain.services.quota_manager import QuotaManager
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.domain.value_objects.publish_result import PublishResult
from src.infrastructure.browser.mock_browser import MockBrowserAdapter
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


def _post(row: int, keyword: str, **kwargs) -> Post:
    defaults = dict(
        status=PostStatus.PENDING,
        content=PostContent(title="제목", body_markdown="## 본문\n" + "x" * 3000),
        quality_score=80,
    )
    defaults.update(kwargs)
    return Post(row_index=row, keyword=keyword, **defaults)


def _use_case(repo, browser, daily_limit=15, max_posts=5):
    return PublishPostsUseCase(
        repo=repo, browser=browser,
        enricher=InternalLinkEnricher(InternalLinkService()),
        policy=PublishPolicy(max_posts=max_posts),
        quota=QuotaManager(daily_limit=daily_limit),
        max_posts=max_posts,
    )


class ScriptedBrowser(MockBrowserAdapter):
    """키워드별로 발행 결과를 정한다. 값이 Exception이면 던진다."""

    def __init__(self, outcomes: dict[str, object]):
        super().__init__()
        self._outcomes = outcomes

    def publish(self, post: Post) -> PublishResult:
        self.published_posts.append(post)
        outcome = self._outcomes.get(post.keyword, PublishResult.ok("https://t.tistory.com/1"))
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, PublishResult)
        return outcome


class TestDailyQuota:
    def test_한도1_대기3이면_1건만_발행하고_나머지는_발행대기_유지(self):
        repo = InMemoryPostRepository(
            [_post(2, "OAuth 개념"), _post(3, "SAML 인증 흐름"), _post(4, "Kafka 파티션")],
        )
        browser = MockBrowserAdapter()

        stats = _use_case(repo, browser, daily_limit=1).execute()

        assert stats.published == 1
        assert len(browser.published_posts) == 1
        statuses = [p.status for p in repo.all()]
        assert statuses.count(PostStatus.PUBLISHED) == 1
        assert statuses.count(PostStatus.PENDING) == 2

    def test_오늘_발행분을_빼고_남은_한도만큼만(self):
        done = _post(9, "이미 발행", status=PostStatus.PUBLISHED, published_at=datetime.now())
        repo = InMemoryPostRepository(
            [done, _post(2, "OAuth 개념"), _post(3, "SAML 인증 흐름"), _post(4, "Kafka 파티션")],
        )
        browser = MockBrowserAdapter()

        stats = _use_case(repo, browser, daily_limit=3).execute()

        assert stats.published == 2

    def test_한도_소진이면_브라우저를_열지도_발행하지도_않는다(self):
        done = _post(9, "이미 발행", status=PostStatus.PUBLISHED, published_at=datetime.now())
        repo = InMemoryPostRepository([done, _post(2, "OAuth 개념")])
        browser = MockBrowserAdapter()

        stats = _use_case(repo, browser, daily_limit=1).execute()

        assert stats.published == 0
        assert browser.published_posts == []
        assert browser.started is False
        assert repo.all()[1].status == PostStatus.PENDING

    def test_플랫폼_한도_응답은_발행대기_유지하고_배치_중단(self):
        limit_msg = "하루에 새롭게 공개 발행할 수 있는 글은 최대 15개까지입니다."
        repo = InMemoryPostRepository([_post(2, "OAuth 개념"), _post(3, "SAML 인증 흐름")])
        browser = MockBrowserAdapter(publish_error=limit_msg)

        stats = _use_case(repo, browser).execute()

        assert len(browser.published_posts) == 1  # 첫 글에서 멈춤
        assert stats.failed == 0
        assert [p.status for p in repo.all()] == [PostStatus.PENDING, PostStatus.PENDING]


class TestBatchDuplicates:
    def test_같은_키워드_대기_2건은_둘_다_게시되지_않는다(self):
        repo = InMemoryPostRepository([_post(2, "OAuth 개념"), _post(3, "OAuth 개념")])
        browser = MockBrowserAdapter()

        stats = _use_case(repo, browser).execute()

        assert stats.published == 1
        assert len(browser.published_posts) == 1
        second = repo.all()[1]
        assert second.status == PostStatus.HOLD
        assert "OAuth 개념" in second.error_message

    def test_유사도_0_7_이상도_같은_배치_중복(self):
        repo = InMemoryPostRepository(
            [_post(2, "kafka 파티션 설계 방법"), _post(3, "kafka 파티션 설계 원칙")],
        )
        browser = MockBrowserAdapter()

        _use_case(repo, browser).execute()

        assert len(browser.published_posts) == 1
        assert repo.all()[1].status == PostStatus.HOLD

    def test_앞_글이_확실히_실패하면_뒤_글은_이번엔_건너뛰고_발행대기_유지(self):
        repo = InMemoryPostRepository([_post(2, "OAuth 개념"), _post(3, "oauth 개념")])
        browser = ScriptedBrowser({"OAuth 개념": PublishResult.fail("제목 입력 실패")})

        _use_case(repo, browser).execute()

        assert len(browser.published_posts) == 1
        first, second = repo.all()
        assert first.status == PostStatus.FAILED
        assert second.status == PostStatus.PENDING

    def test_앞_글_결과가_불명이면_뒤_글은_발행하지_않고_보류(self):
        repo = InMemoryPostRepository([_post(2, "OAuth 개념"), _post(3, "OAuth 개념")])
        browser = ScriptedBrowser({"OAuth 개념": RuntimeError("chromedriver crashed")})

        _use_case(repo, browser).execute()

        assert len(browser.published_posts) == 1
        first, second = repo.all()
        assert first.status == PostStatus.FAILED
        assert PUBLISH_UNCONFIRMED in first.error_message
        assert second.status == PostStatus.HOLD

    def test_이전_실행의_결과_불명_글과_같은_키워드도_보류(self):
        unknown = _post(2, "OAuth 개념", status=PostStatus.FAILED,
                        error_message=f"{PUBLISH_UNCONFIRMED}: 중단")
        repo = InMemoryPostRepository([unknown, _post(3, "OAuth 개념")])
        browser = MockBrowserAdapter()

        _use_case(repo, browser).execute()

        assert browser.published_posts == []
        assert repo.all()[1].status == PostStatus.HOLD


class CountingRepo(InMemoryPostRepository):
    def __init__(self, posts):
        super().__init__(posts)
        self.reads = 0

    def find_all(self):
        self.reads += 1
        return super().find_all()

    def find_pending(self, limit: int = 5):
        self.reads += 1
        return super().find_pending(limit)


class TestIneligibleHead:
    def test_앞_5건이_부적격이어도_6번째를_발행(self):
        bad = [_post(i, f"불량 {i}", quality_score=10) for i in range(2, 7)]
        good = _post(7, "OAuth 개념")
        repo = CountingRepo([*bad, good])
        browser = MockBrowserAdapter()

        stats = _use_case(repo, browser, max_posts=5).execute()

        assert stats.published == 1
        assert browser.published_posts[0].keyword == "OAuth 개념"
        assert stats.skipped == 5
        assert repo.reads == 1  # 시트 전체 읽기 1회로 판단


class FailingSaveRepo(InMemoryPostRepository):
    """발행완료 저장만 실패하는 시트 — 외부 발행은 됐는데 기록을 못 한 상황."""

    def save(self, post: Post) -> None:
        if post.status == PostStatus.PUBLISHED:
            raise ConnectionError("Sheets 503")
        super().save(post)


class TestSaveFailureAfterPublish:
    def test_발행_후_저장_실패면_다음_실행에서_자동_재발행하지_않는다(self):
        post = _post(2, "OAuth 개념")
        repo = FailingSaveRepo([post])
        browser = MockBrowserAdapter()

        with pytest.raises(ConnectionError):
            _use_case(repo, browser).execute()
        assert len(browser.published_posts) == 1

        # 다음 실행: 고스트 복구(재시도 켬) → 발행
        ResetStuckPostsUseCase(repo=repo, retry_failed=True).execute()
        stuck = repo.all()[0]
        assert stuck.status == PostStatus.FAILED
        assert PUBLISH_UNCONFIRMED in stuck.error_message
        _use_case(repo, browser).execute()

        assert len(browser.published_posts) == 1
