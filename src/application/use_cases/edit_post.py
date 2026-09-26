"""EditPostUseCase — 관리자가 발행 전 글을 고치고, 실패·보류 글을 발행대기로 되돌린다."""
from __future__ import annotations

from dataclasses import replace

from src.domain.entities.post import Post
from src.domain.exceptions import InvalidStatusTransitionError
from src.domain.ports.post_repository import PostRepository
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus

# 발행됐거나 발행 중인 글은 시트만 고쳐도 블로그 글과 어긋나므로 막는다
EDITABLE_STATUSES = frozenset({PostStatus.PENDING, PostStatus.HOLD, PostStatus.FAILED})


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
        return post

    def restore(self, row_index: int) -> Post:
        post = self._find(row_index)
        if post is None:
            raise PostNotEditableError(f"{row_index}행이 없습니다")
        if post.status == PostStatus.FAILED:
            post.reset_failed_to_pending()
        elif post.status == PostStatus.HOLD:
            post.release_hold()
        else:
            raise InvalidStatusTransitionError(post.status, PostStatus.PENDING)
        self._repo.save(post)
        return post

    def _find(self, row_index: int) -> Post | None:
        return next((p for p in self._repo.find_all() if p.row_index == row_index), None)
