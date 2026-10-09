"""CheckIndexingUseCase 테스트 — 미색인 사유 분류와 수정 순환 방지."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.application.use_cases.check_indexing import CheckIndexingUseCase
from src.domain.entities.post import Post
from src.domain.ports.seo_port import IndexingPort, IndexingResult
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository

URL = "https://example.tistory.com/1"
NOW = datetime(2026, 10, 8, 14, 0)


class _StubIndexing(IndexingPort):
    """테스트용 IndexingPort 스텁."""

    def __init__(self, result: IndexingResult):
        self._result = result
        self.calls = 0

    def check(self, url: str) -> IndexingResult:
        self.calls += 1
        return self._result


def _published_post(row: int = 2, days_ago: int = 60) -> Post:
    post = Post(row_index=row, keyword="테스트")
    post.status = PostStatus.PUBLISHED
    post.published_url = URL
    post.published_at = NOW - timedelta(days=days_ago)
    return post


def _run(post: Post, **result_fields):
    result = IndexingResult(url=URL, **result_fields)
    repo = InMemoryPostRepository([post])
    uc = CheckIndexingUseCase(repo, indexing=_StubIndexing(result), clock=lambda: NOW)
    return uc.execute(post)


CRAWLED = {"verdict": "NEUTRAL", "coverage_state": "Crawled - currently not indexed",
           "page_fetch_state": "SUCCESSFUL", "robots_txt_state": "ALLOWED",
           "indexing_state": "INDEXING_ALLOWED"}


def test_색인됨_포스트_상태유지():
    post = _published_post()
    result = _run(post, is_indexed=True, verdict="PASS", coverage_state="Submitted and indexed")
    assert result.success and result.is_indexed and not result.marked_revision
    assert result.category == "색인됨"
    assert post.status == PostStatus.PUBLISHED


@pytest.mark.parametrize(("fields", "category"), [
    ({"verdict": "NEUTRAL", "coverage_state": "Discovered - currently not indexed"}, "수집 지연"),
    ({"verdict": "NEUTRAL", "coverage_state": "URL is unknown to Google"}, "수집 지연"),
    ({"verdict": "FAIL", "coverage_state": "Blocked by robots.txt",
      "robots_txt_state": "DISALLOWED"}, "robots·noindex 차단"),
    ({"verdict": "FAIL", "coverage_state": "Excluded by 'noindex' tag",
      "indexing_state": "BLOCKED_BY_META_TAG"}, "robots·noindex 차단"),
    ({"verdict": "NEUTRAL", "coverage_state": "Duplicate, Google chose different canonical "
      "than user"}, "canonical·중복"),
    ({**CRAWLED, "google_canonical": "https://example.tistory.com/m/1",
      "user_canonical": URL}, "canonical·중복"),
    ({"verdict": "FAIL", "coverage_state": "Not found (404)",
      "page_fetch_state": "NOT_FOUND"}, "접근 오류"),
    ({"verdict": "FAIL", "coverage_state": "Server error (5xx)",
      "page_fetch_state": "SERVER_ERROR"}, "접근 오류"),
    ({"verdict": "FAIL", "page_fetch_state": "ACCESS_FORBIDDEN"}, "접근 오류"),
    ({"verdict": "NEUTRAL", "coverage_state": "알 수 없는 상태"}, "미분류"),
])
def test_콘텐츠_문제가_아닌_미색인은_수정대기로_바꾸지_않고_사유만_남긴다(fields, category):
    post = _published_post()
    result = _run(post, **fields)
    assert result.success and not result.is_indexed
    assert result.category == category
    assert not result.marked_revision
    assert post.status == PostStatus.PUBLISHED
    assert category in post.error_message


def test_크롤링됨_미색인_유예_지남은_콘텐츠_문제로_수정대기_후보():
    post = _published_post(days_ago=60)
    result = _run(post, **CRAWLED)
    assert result.category == "콘텐츠 문제"
    assert result.marked_revision
    assert post.status == PostStatus.REVISION_PENDING
    assert "Crawled - currently not indexed" in post.error_message


def test_발행_후_유예기간_안이면_API를_부르지_않는다():
    post = _published_post(days_ago=3)
    stub = _StubIndexing(IndexingResult(url=URL, **CRAWLED))
    uc = CheckIndexingUseCase(InMemoryPostRepository([post]), indexing=stub, clock=lambda: NOW)
    result = uc.execute(post)
    assert stub.calls == 0
    assert not result.success and not result.error and not result.marked_revision
    assert post.status == PostStatus.PUBLISHED


def test_마지막_수정_뒤_냉각기간_안이면_콘텐츠_문제라도_재전환_안함():
    # 수정 기록(revised_at)이 발행일보다 최근이면 그 날짜가 기준이다
    post = _published_post(days_ago=90)
    post.revision_count = 0
    post.revised_at = NOW - timedelta(days=20)
    result = _run(post, **CRAWLED)
    assert result.category == "콘텐츠 문제"
    assert not result.marked_revision
    assert post.status == PostStatus.PUBLISHED
    assert "사람 확인" in post.error_message


def test_자동_수정_횟수_한도를_넘으면_재전환_안함():
    post = _published_post(days_ago=200)
    post.revision_count = 1
    post.revised_at = NOW - timedelta(days=100)
    result = _run(post, **CRAWLED)
    assert not result.marked_revision
    assert post.status == PostStatus.PUBLISHED
    assert "사람 확인" in post.error_message


def test_같은_글을_매일_점검해도_한_번만_수정대기로_간다():
    # 수정 발행 뒤 시트에는 revised_at=지금, revision_count+1이 남는다(발행일은 그대로)
    post = _published_post(days_ago=60)
    first_published = post.published_at
    repo = InMemoryPostRepository([post])
    uc = CheckIndexingUseCase(repo, _StubIndexing(IndexingResult(url=URL, **CRAWLED)),
                              clock=lambda: NOW)
    assert uc.execute(post).marked_revision
    post.mark_revising()
    post.mark_revised(URL)
    post.published_at = first_published
    post.revised_at = NOW
    post.revision_count = 1
    for day in range(1, 60):
        later = CheckIndexingUseCase(repo, _StubIndexing(IndexingResult(url=URL, **CRAWLED)),
                                     clock=lambda d=day: NOW + timedelta(days=d))
        assert not later.execute(post).marked_revision
    assert post.status == PostStatus.PUBLISHED


def test_미발행_포스트_실패():
    uc = CheckIndexingUseCase(InMemoryPostRepository(), indexing=_StubIndexing(
        IndexingResult(url="")))
    result = uc.execute(Post(row_index=2, keyword="테스트"))
    assert result.success is False
    assert "발행완료 상태가 아닙니다" in result.error


def test_URL_없는_포스트_실패():
    uc = CheckIndexingUseCase(InMemoryPostRepository(), indexing=_StubIndexing(
        IndexingResult(url="")))
    post = Post(row_index=2, keyword="테스트")
    post.status = PostStatus.PUBLISHED
    result = uc.execute(post)
    assert result.success is False
    assert "발행 URL이 없습니다" in result.error


def test_API_오류시_실패():
    post = _published_post()
    result = _run(post, error="403 Forbidden")
    assert result.success is False
    assert "403" in result.error
    assert post.status == PostStatus.PUBLISHED


def test_최근_수정한_글은_최초_발행일이_오래돼도_건너뛴다():
    # 수정 발행은 published_at(최초 발행일)을 두고 revised_at만 바꾼다 — 유예는 늦은 쪽 기준
    post = _published_post(days_ago=60)
    post.revised_at = NOW - timedelta(days=2)
    result = _run(post, is_indexed=False, **CRAWLED)
    assert not result.marked_revision
    assert post.status == PostStatus.PUBLISHED
