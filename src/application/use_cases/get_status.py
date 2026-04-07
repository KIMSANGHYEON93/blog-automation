"""GetStatusUseCase — 블로그 현황 대시보드 데이터 집계."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.domain.ports.post_repository import PostRepository
from src.domain.value_objects.post_status import PostStatus

logger = logging.getLogger(__name__)


@dataclass
class StatusReport:
    """상태 대시보드 DTO."""

    total: int = 0
    pending: int = 0
    published: int = 0
    failed: int = 0
    revision_pending: int = 0
    other: int = 0

    # 색인 (CWV 점검 완료 포스트 중 비율)
    cwv_checked: int = 0
    cwv_passed: int = 0

    # CWV 평균
    avg_lcp: float = 0.0
    avg_cls: float = 0.0
    avg_score: float = 0.0


class GetStatusUseCase:
    """전체 포스트 현황을 집계하여 StatusReport 반환."""

    def __init__(self, repo: PostRepository):
        self._repo = repo

    def execute(self) -> StatusReport:
        posts = self._repo.find_all()
        report = StatusReport(total=len(posts))

        for post in posts:
            if post.status == PostStatus.PENDING:
                report.pending += 1
            elif post.status == PostStatus.PUBLISHED:
                report.published += 1
            elif post.status == PostStatus.FAILED:
                report.failed += 1
            elif post.status == PostStatus.REVISION_PENDING:
                report.revision_pending += 1
            else:
                report.other += 1

        # CWV 데이터 집계 — Post 엔티티의 cwv_lcp/cwv_cls 필드 기반
        cwv_checked_posts = [
            p for p in posts
            if p.status == PostStatus.PUBLISHED
            and p.published_url
            and p.cwv_lcp is not None
        ]
        report.cwv_checked = len(cwv_checked_posts)

        if cwv_checked_posts:
            lcp_threshold = 2.5
            report.cwv_passed = sum(
                1 for p in cwv_checked_posts
                if p.cwv_lcp is not None
                and p.cwv_lcp < lcp_threshold
            )
            lcp_values = [
                p.cwv_lcp for p in cwv_checked_posts
                if p.cwv_lcp is not None
            ]
            if lcp_values:
                report.avg_lcp = sum(lcp_values) / len(lcp_values)
            cls_values = [
                p.cwv_cls for p in cwv_checked_posts
                if p.cwv_cls is not None
            ]
            if cls_values:
                report.avg_cls = sum(cls_values) / len(cls_values)

        return report

    def format_report(self, report: StatusReport) -> str:
        """터미널 출력용 포맷."""
        lines = [
            "=== Blog Automation Status ===",
            f"Total: {report.total}  |  "
            f"발행대기: {report.pending}  |  "
            f"발행완료: {report.published}  |  "
            f"실패: {report.failed}",
        ]
        if report.revision_pending > 0:
            lines.append(f"수정대기: {report.revision_pending}")
        if report.cwv_checked > 0:
            pass_rate = (
                f"{report.cwv_passed}/{report.cwv_checked} "
                f"({report.cwv_passed / report.cwv_checked * 100:.1f}%)"
                if report.cwv_checked > 0 else "N/A"
            )
            lines.append(f"CWV Pass: {pass_rate}")
        if report.avg_lcp > 0:
            lines.append(
                f"Avg LCP: {report.avg_lcp:.1f}s  |  "
                f"Avg CLS: {report.avg_cls:.2f}  |  "
                f"Avg Score: {report.avg_score:.0f}"
            )
        return "\n".join(lines)
