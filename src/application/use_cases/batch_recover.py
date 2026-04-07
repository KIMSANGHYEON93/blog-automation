"""BatchRecoverUseCase — Bulk recovery of failed posts using ErrorClassifier."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.domain.ports.post_repository import PostRepository
from src.domain.services.error_classifier import ErrorClassifier
from src.domain.value_objects.publish_error import PublishError

logger = logging.getLogger(__name__)


@dataclass
class RecoverResult:
    """일괄 복구 결과 DTO."""
    recovered: int = 0
    skipped_manual: int = 0
    skipped_revision: int = 0
    total_failed: int = 0
    details: list[tuple[int, str, PublishError]] = field(default_factory=list)


class BatchRecoverUseCase:
    """발행실패 포스트를 ErrorClassifier로 분류 후 자동 복구 가능한 건만 발행대기로 전환."""

    def __init__(self, repo: PostRepository):
        self._repo = repo
        self._classifier = ErrorClassifier()

    def execute(self, *, force_unknown: bool = False) -> RecoverResult:
        """발행실패 포스트를 일괄 복구.

        1. find_failed()로 전체 실패 포스트 조회
        2. ErrorClassifier로 에러 유형 분류
        3. 자동 복구 가능한 건만 reset_failed_to_pending()
        4. force_unknown=True 시 unknown 유형도 강제 복구
        5. 통계 반환
        """
        result = RecoverResult()
        failed_posts = self._repo.find_failed()
        result.total_failed = len(failed_posts)

        if not failed_posts:
            logger.info("복구 대상 실패 포스트 없음")
            return result

        for post in failed_posts:
            classified = self._classifier.classify(post.error_message)
            result.details.append((post.row_index, post.keyword, classified))

            should_recover = classified.should_auto_recover or (
                force_unknown and classified.error_type.value == "unknown"
            )

            if should_recover:
                if post.was_previously_published():
                    post.reset_failed_to_revision_pending()
                    target = "수정대기"
                else:
                    post.reset_failed_to_pending()
                    target = "발행대기"
                self._repo.save(post)
                result.recovered += 1
                label = "강제 복구" if not classified.should_auto_recover else "자동 복구"
                logger.info(
                    f"{label}: row={post.row_index}, keyword={post.keyword}, "
                    f"type={classified.error_type.value} → {target}"
                )
            elif classified.action.value == "mark_revision":
                result.skipped_revision += 1
                logger.info(
                    f"수정 필요 (건너뜀): row={post.row_index}, keyword={post.keyword}"
                )
            else:
                result.skipped_manual += 1
                logger.info(
                    f"수동 개입 필요 (건너뜀): row={post.row_index}, "
                    f"keyword={post.keyword}, type={classified.error_type.value}"
                )

        logger.info(
            f"일괄 복구 완료: 복구={result.recovered}, "
            f"수동={result.skipped_manual}, 수정필요={result.skipped_revision}, "
            f"전체={result.total_failed}"
        )
        return result
