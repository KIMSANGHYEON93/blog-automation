"""EditPostUseCase — 관리자가 발행 전 글을 고치고, 실패·보류 글을 발행대기로 되돌린다."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from src.domain.entities.post import Post
from src.domain.exceptions import InvalidStatusTransitionError
from src.domain.ports.post_repository import PostRepository
from src.domain.services.photo_markers import insert_photo_marker
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
        # 브라우저 textarea는 \r\n을 보낸다 — 줄 단위 표시([[사진:…]])를 알아보도록 \n으로 통일
        body = body.replace("\r\n", "\n")
        post.content = replace(
            post.content or PostContent(), title=title, body_markdown=body, tags=tags,
        )
        post.category = category
        self._repo.save_content(post)
        if post.status == PostStatus.PUBLISHED:
            post.mark_revision_pending("대시보드에서 수정 — 수정 발행 대기")
            self._repo.save(post)
        return post

    def add_photo(self, row_index: int, filename: str) -> Post:
        """올린 사진 표시를 본문에 넣는다. 저장 규칙(상태 검사·수정대기 전환)은 edit와 같다."""
        post = self._find(row_index)
        if post is None or post.content is None:
            raise PostNotEditableError(f"{row_index}행은 편집할 수 없는 상태입니다")
        return self.edit(
            row_index, title=post.content.title or "", tags=post.content.tags,
            body=insert_photo_marker(post.content.body_markdown or "", filename),
            category=post.category,
        )

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

    def regenerate(self, row_index: int) -> Post:
        """미발행 글을 대기로 돌린다. 다음 '지금 생성'이 같은 키워드로 내용을 덮어쓴다."""
        return self._transition(row_index, lambda post: post.reset_for_regeneration())

    def archive(self, row_index: int) -> Post:
        """발행대기 글을 보류로 빼 둔다. 시트 행은 남고 '되돌리기'로 다시 살린다."""
        return self._transition(row_index, lambda post: post.mark_hold("대시보드에서 보관"))

    def _transition(self, row_index: int, change: Callable[[Post], None]) -> Post:
        post = self._find(row_index)
        if post is None:
            raise PostNotEditableError(f"{row_index}행이 없습니다")
        change(post)
        self._repo.save(post)
        return post

    def _find(self, row_index: int) -> Post | None:
        return next((p for p in self._repo.find_all() if p.row_index == row_index), None)
