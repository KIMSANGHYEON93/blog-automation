"""CheckIndexingUseCase — 발행 포스트의 Google 색인 상태 점검.

URL Inspection 결과로 미색인 사유를 분류한다. 수집 지연·robots/noindex·canonical·접근 오류는
글을 고쳐도 풀리지 않으므로 사유만 기록하고, '크롤링됨 - 색인 안 됨'(콘텐츠 문제)만
수정대기 후보로 보낸다. 같은 글을 효과 없이 반복 수정하지 않도록 냉각 기간과 횟수 한도를 둔다.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.entities.post import Post
from src.domain.ports.post_repository import PostRepository
from src.domain.ports.seo_port import IndexingPort, IndexingResult
from src.domain.value_objects.post_status import PostStatus

logger = logging.getLogger(__name__)

# 발행·수정 뒤 이 기간 안에는 색인 점검을 하지 않는다 — 구글 수집은 며칠~몇 주 걸린다
REINDEX_GRACE = timedelta(days=14)
# 콘텐츠 문제로 자동 수정대기를 보내는 조건: 마지막 발행·수정 뒤 이만큼 지났고,
REVISION_COOLDOWN = timedelta(days=30)
# 자동 수정이 이 횟수 미만일 때만. 그 뒤로는 사람이 글을 직접 보강해야 한다
# (--revise는 본문을 새로 쓰지 않고 시트 본문을 다시 올리므로 반복해도 효과가 없다)
MAX_AUTO_REVISIONS = 1

INDEXED = "색인됨"
DELAY = "수집 지연"
BLOCKED = "robots·noindex 차단"
CANONICAL = "canonical·중복"
ACCESS = "접근 오류"
CONTENT = "콘텐츠 문제"
UNKNOWN = "미분류"

_FETCH_OK = {"", "SUCCESSFUL", "PAGE_FETCH_STATE_UNSPECIFIED"}
_ACCESS_WORDS = ("404", "5xx", "server error", "access forbidden", "unauthorized",
                 "blocked due to")
_CANONICAL_WORDS = ("canonical", "duplicate", "redirect")


def _same_url(a: str, b: str) -> bool:
    return a.rstrip("/") == b.rstrip("/")


def classify(result: IndexingResult, url: str) -> str:
    """URL Inspection 결과를 미색인 사유 범주로 나눈다."""
    if result.is_indexed:
        return INDEXED
    coverage = result.coverage_state.lower()
    if result.page_fetch_state == "BLOCKED_ROBOTS_TXT":
        return BLOCKED
    if result.page_fetch_state not in _FETCH_OK or any(w in coverage for w in _ACCESS_WORDS):
        return ACCESS
    if (result.robots_txt_state == "DISALLOWED"
            or result.indexing_state.startswith("BLOCKED_")
            or "noindex" in coverage or "robots.txt" in coverage):
        return BLOCKED
    declared = result.user_canonical or url
    if any(w in coverage for w in _CANONICAL_WORDS) or (
            result.google_canonical and not _same_url(result.google_canonical, declared)):
        return CANONICAL
    if "crawled - currently not indexed" in coverage:
        return CONTENT
    if "discovered" in coverage or "unknown to google" in coverage:
        return DELAY
    return UNKNOWN


def last_changed(post: Post) -> datetime | None:
    """마지막 발행·수정 시각. 수정 발행은 발행일을 바꾸지 않고 revised_at만 남긴다."""
    dates = [d for d in (post.published_at, post.revised_at) if d]
    return max(dates) if dates else None


@dataclass
class IndexingCheckResult:
    """색인 점검 결과 DTO."""

    success: bool
    post_keyword: str
    url: str
    is_indexed: bool
    verdict: str = ""
    coverage_state: str = ""
    category: str = ""
    marked_revision: bool = False
    error: str = ""


class CheckIndexingUseCase:
    """발행 완료 포스트의 Google 색인 상태를 점검하고 미색인 사유를 기록한다."""

    def __init__(
        self, repo: PostRepository, indexing: IndexingPort,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self._repo = repo
        self._indexing = indexing
        self._clock = clock

    def execute(self, post: Post) -> IndexingCheckResult:
        """단일 포스트의 색인 상태 점검."""
        base = IndexingCheckResult(
            success=False, post_keyword=post.keyword, url=post.published_url, is_indexed=False,
        )
        if post.status != PostStatus.PUBLISHED:
            base.error = f"발행완료 상태가 아닙니다: {post.status.value}"
            return base
        if not post.published_url:
            base.error = "발행 URL이 없습니다"
            return base

        now = self._clock()
        last = last_changed(post)
        if last and now - last < REINDEX_GRACE:
            logger.info(f"최근 발행·수정 — 색인 점검 건너뜀: {post.keyword}")
            return base

        result: IndexingResult = self._indexing.check(post.published_url)
        if result.error:
            base.error = result.error
            return base

        category = classify(result, post.published_url)
        base.success = True
        base.is_indexed = result.is_indexed
        base.verdict = result.verdict
        base.coverage_state = result.coverage_state
        base.category = category
        if category == INDEXED:
            return base

        detail = result.coverage_state or result.page_fetch_state or result.verdict
        reason = f"색인 진단[{category}]: {detail}"
        if category == CONTENT:
            blocked_by = self._revision_block(post, now)
            if not blocked_by:
                post.mark_revision_pending(f"{reason} — 본문 보강 필요")
                self._repo.save(post)
                base.marked_revision = True
                logger.info(f"콘텐츠 문제 → 수정대기: {post.keyword} ({detail})")
                return base
            reason = f"{reason} — {blocked_by}, 사람 확인 필요"

        logger.info(f"미색인 사유 기록(상태 유지): {post.keyword} — {reason}")
        if post.error_message != reason[:200]:
            post.error_message = reason[:200]
            self._repo.save(post)
        return base

    @staticmethod
    def _revision_block(post: Post, now: datetime) -> str:
        """자동 수정대기를 막는 이유. 막을 이유가 없으면 빈 문자열."""
        if post.revision_count >= MAX_AUTO_REVISIONS:
            return f"자동 수정 {post.revision_count}회 이미 함"
        last = last_changed(post)
        if last and now - last < REVISION_COOLDOWN:
            return f"마지막 발행·수정 뒤 {REVISION_COOLDOWN.days}일 안 됨"
        return ""
