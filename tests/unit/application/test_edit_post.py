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


@pytest.mark.parametrize("status", [PostStatus.PUBLISHING, PostStatus.REVISING])
def test_발행_중이거나_수정_중인_글은_고칠_수_없다(status):
    repo = _repo(status)
    with pytest.raises(PostNotEditableError):
        EditPostUseCase(repo).edit(5, title="t", body="b", tags="", category="")
    assert _get(repo).content.title == "옛 제목"


def test_브라우저가_보낸_CRLF_줄바꿈은_LF로_저장한다():
    # 아이폰 textarea는 \r\n을 보낸다 — 그대로 두면 [[사진:…]] 줄을 못 알아본다(2026-10-06)
    repo = _repo()
    EditPostUseCase(repo).edit(5, title="t", body="가.\r\n\r\n[[사진:a1.jpg]]\r\n", tags="",
                               category="c")
    assert _get(repo).content.body_markdown == "가.\n\n[[사진:a1.jpg]]\n"


def test_사진을_올리면_본문에_표시를_넣는다():
    repo = _repo()
    EditPostUseCase(repo).add_photo(5, "a1.jpg")
    post = _get(repo)
    assert post.content.body_markdown == "옛 본문\n\n[[사진:a1.jpg]]"
    assert post.content.title == "옛 제목"  # 다른 필드는 그대로


def test_발행된_글에_사진을_올리면_수정대기가_된다():
    repo = _repo(PostStatus.PUBLISHED)
    EditPostUseCase(repo).add_photo(5, "a1.jpg")
    assert _get(repo).status == PostStatus.REVISION_PENDING


def test_발행된_글을_고치면_수정대기가_된다():
    # 시트만 고치면 블로그 글과 어긋난다 — 수정대기로 돌려 '수정 발행'을 기다린다
    repo = _repo(PostStatus.PUBLISHED)
    EditPostUseCase(repo).edit(5, title="새 제목", body="b", tags="", category="꿀팁")
    post = _get(repo)
    assert post.status == PostStatus.REVISION_PENDING
    assert (post.content.title, post.category) == ("새 제목", "꿀팁")


def test_수정대기_글은_다시_고쳐도_수정대기():
    repo = _repo(PostStatus.REVISION_PENDING)
    EditPostUseCase(repo).edit(5, title="t", body="b", tags="", category="")
    assert _get(repo).status == PostStatus.REVISION_PENDING


def test_발행했던_글의_실패는_수정대기로_되돌린다():
    # 발행대기로 되돌리면 새 글로 한 번 더 발행돼 중복 글이 생긴다
    repo = _repo(PostStatus.FAILED)
    post = _get(repo)
    post.published_url, post.entry_id = "https://blog.naver.com/b/1", "1"
    EditPostUseCase(repo).restore(5)
    assert _get(repo).status == PostStatus.REVISION_PENDING


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


@pytest.mark.parametrize("status", [PostStatus.PENDING, PostStatus.HOLD, PostStatus.FAILED])
def test_발행_전_글은_다시_생성하도록_대기로_돌린다(status):
    repo = _repo(status)
    EditPostUseCase(repo).regenerate(5)
    assert _get(repo).status == PostStatus.WAITING


def test_발행된_적_있는_글은_다시_생성하지_않는다():
    # 대기로 돌리면 n8n이 새 글을 만들고 또 발행돼 중복 글이 생긴다
    repo = _repo(PostStatus.FAILED)
    _get(repo).published_url = "https://blog.naver.com/b/1"
    with pytest.raises(InvalidStatusTransitionError):
        EditPostUseCase(repo).regenerate(5)
    with pytest.raises(InvalidStatusTransitionError):
        EditPostUseCase(_repo(PostStatus.PUBLISHED)).regenerate(5)


def test_발행대기는_보관하면_보류():
    repo = _repo()
    EditPostUseCase(repo).archive(5)
    assert _get(repo).status == PostStatus.HOLD
    with pytest.raises(InvalidStatusTransitionError):
        EditPostUseCase(repo).archive(5)
