"""EditPostUseCase — 대시보드 게시물 편집과 상태 복구."""
import pytest

from src.application.use_cases.edit_post import EditPostUseCase, PostNotEditableError
from src.domain.entities.post import Post
from src.domain.exceptions import InvalidStatusTransitionError
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


def _repo(status=PostStatus.PENDING):
    post = Post(
        row_index=5, keyword="감마", status=status, category="TechNova", quality_score=92,
        content=PostContent(title="옛 제목", body_markdown="옛 본문", tags="a, b",
                            meta_description="요약"),
    )
    return InMemoryPostRepository([post])


def _get(repo, row=5):
    return next(p for p in repo.find_all() if p.row_index == row)


def test_제목_본문_태그_카테고리를_고친다():
    repo = _repo()
    EditPostUseCase(repo).edit(5, title="새 제목", body="새 본문", tags="x, y", category="꿀팁")
    post = _get(repo)
    assert (post.content.title, post.content.body_markdown, post.content.tags) == (
        "새 제목", "새 본문", "x, y",
    )
    assert post.category == "꿀팁"
    assert post.content.meta_description == "요약"  # 폼에 없는 필드는 그대로
    assert post.status == PostStatus.PENDING


@pytest.mark.parametrize("status", [PostStatus.HOLD, PostStatus.FAILED])
def test_보류와_실패_글도_고칠_수_있다(status):
    repo = _repo(status)
    EditPostUseCase(repo).edit(5, title="t", body="b", tags="", category="")
    assert _get(repo).content.title == "t"


@pytest.mark.parametrize("status", [PostStatus.PUBLISHED, PostStatus.PUBLISHING])
def test_발행된_글이나_발행_중인_글은_고칠_수_없다(status):
    repo = _repo(status)
    with pytest.raises(PostNotEditableError):
        EditPostUseCase(repo).edit(5, title="t", body="b", tags="", category="")
    assert _get(repo).content.title == "옛 제목"


def test_없는_행은_편집_불가():
    with pytest.raises(PostNotEditableError):
        EditPostUseCase(_repo()).edit(99, title="t", body="b", tags="", category="")


@pytest.mark.parametrize("status", [PostStatus.FAILED, PostStatus.HOLD])
def test_실패와_보류는_발행대기로_되돌린다(status):
    repo = _repo(status)
    EditPostUseCase(repo).restore(5)
    assert _get(repo).status == PostStatus.PENDING


def test_발행대기는_되돌릴_게_없다():
    with pytest.raises(InvalidStatusTransitionError):
        EditPostUseCase(_repo()).restore(5)
