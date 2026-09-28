"""EditPostUseCase — 관리자가 발행 전 글을 고치고, 실패·보류 글을 발행대기로 되돌린다."""
from __future__ import annotations

from dataclasses import replace

from src.domain.entities.post import Post
from src.domain.exceptions import InvalidStatusTransitionError
from src.domain.ports.post_repository import PostRepository
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus

# 발행·수정 중인 글은 막는다. 발행된 글은 고치면 수정대기가 되어 '수정 발행'을 기다린다
# (시트만 고친 채 두면 블로그 글과 어긋난다)
EDITABLE_STATUSES = frozenset({
    PostStatus.PENDING, PostStatus.HOLD, PostStatus.FAILED,
    PostStatus.PUBLISHED, PostStatus.REVISION_PENDING,
})


class PostNotEditableError(Exception):
    pass


class EditPostUseCase:
    def __init__(self, repo: PostRepository):
        self._repo = repo

    def edit(self, row_index: int, *, title: str, body: str, tags: str, category: str) -> Post:
        post = self._find(row_index)
        if post is None or post.status not in EDITABLE_STATUSES:
            raise PostNotEditableError(f"{row_index}행은 편집할 수 없는 상태입니다")
        post.content = replace(
            post.content or PostContent(), title=title, body_markdown=body, tags=tags,
        )
        post.category = category
        self._repo.save_content(post)
        if post.status == PostStatus.PUBLISHED:
            post.mark_revision_pending("대시보드에서 수정 — 수정 발행 대기")
            self._repo.save(post)
        return post

    def restore(self, row_index: int) -> Post:
        post = self._find(row_index)
        if post is None:
            raise PostNotEditableError(f"{row_index}행이 없습니다")
        if post.status == PostStatus.FAILED and post.was_previously_published():
            post.reset_failed_to_revision_pending()  # 발행대기로 돌리면 새 글로 중복 발행된다
        elif post.status == PostStatus.FAILED:
            post.reset_failed_to_pending()
        elif post.status == PostStatus.HOLD:
            post.release_hold()
        else:
            raise InvalidStatusTransitionError(post.status, PostStatus.PENDING)
        self._repo.save(post)
        return post

    def _find(self, row_index: int) -> Post | None:
        return next((p for p in self._repo.find_all() if p.row_index == row_index), None)
