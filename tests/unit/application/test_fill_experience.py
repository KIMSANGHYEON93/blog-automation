"""EditPostUseCase 빠른 입력 — '직접 해 보니' 자리를 조립한 문단으로 채운다."""
import pytest

from src.application.use_cases.edit_post import EditPostUseCase, PostNotEditableError
from src.domain.entities.post import Post
from src.domain.services.experience_note import ExperienceInputError, ExperienceResult
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository

MARKER = "[[직접 해 보니]] 해 보고 답해 주세요. 확인할 것: 요약이 됐나요? 몇 분까지 됐나요?"
BODY = "## 설정\n\n" + "가" * 3200 + f"\n\n{MARKER}\n\n## 자주 묻는 질문\n\nQ. 무료?"


def _repo(status=PostStatus.PENDING, body=BODY):
    post = Post(
        row_index=5, keyword="감마", status=status, quality_score=92,
        content=PostContent(title="제목", body_markdown=body, tags="a"),
    )
    return InMemoryPostRepository([post])


def _get(repo):
    return next(p for p in repo.find_all() if p.row_index == 5)


def _fill(repo, result=ExperienceResult.WORKED, answers=("예", "30분"), memo=""):
    return EditPostUseCase(repo).fill_experience(5, result, list(answers), memo)


def test_미리보기는_조립한_문단만_돌려주고_저장하지_않는다():
    repo = _repo()
    text = EditPostUseCase(repo).preview_experience(5, ExperienceResult.PARTIAL, ["예", "30분"], "")
    assert text == (
        "이 글의 방법을 제가 직접 해 봤고, 일부만 됐습니다.\n\n"
        "- 요약이 됐나요? → 예\n- 몇 분까지 됐나요? → 30분"
    )
    assert _get(repo).content.body_markdown == BODY


def test_저장하면_표시가_사라지고_발행_차단이_풀린다():
    repo = _repo()
    _fill(repo)
    post = _get(repo)
    assert "[[직접 해 보니]]" not in post.content.body_markdown
    assert "- 몇 분까지 됐나요? → 30분" in post.content.body_markdown
    assert post.content.body_markdown.endswith("## 자주 묻는 질문\n\nQ. 무료?")
    assert post.publish_blockers() == []


def test_검증_뒤_고친_적이_없으면_경험만_채워도_재검증이_필요없다():
    # 바뀐 곳은 사람이 직접 입력한 경험뿐이다 — 30초 입력 뒤 '검수 승인'을 또 요구하지 않는다
    repo = _repo()
    _fill(repo)
    assert not _get(repo).verification_stale()


def test_이미_본문을_고쳐_재검증이_필요하면_그대로_필요하다():
    repo = _repo()
    EditPostUseCase(repo).edit(5, title="제목", body=BODY.replace("가" * 10, "나" * 10, 1),
                               tags="a", category="")
    assert _get(repo).verification_stale()
    _fill(repo)
    assert _get(repo).verification_stale()


@pytest.mark.parametrize("result, answers", [
    (None, ("예", "30분")),
    (ExperienceResult.WORKED, ("예", "")),
    (ExperienceResult.WORKED, ("예",)),  # 질문 수와 다르다 — 화면이 오래됐다
])
def test_결과나_답이_비면_저장하지_않고_차단도_남는다(result, answers):
    repo = _repo()
    with pytest.raises(ExperienceInputError):
        _fill(repo, result=result, answers=answers)
    post = _get(repo)
    assert post.content.body_markdown == BODY
    assert any("직접 해 보니" in r for r in post.publish_blockers())


def test_표시가_없는_글은_채울_수_없다():
    with pytest.raises(ExperienceInputError):
        _fill(_repo(body="본문만"), answers=("예",))


@pytest.mark.parametrize("status", [PostStatus.PUBLISHING, PostStatus.REVISING])
def test_발행_중인_글은_채울_수_없다(status):
    with pytest.raises(PostNotEditableError):
        _fill(_repo(status))


def test_없는_행은_거절한다():
    with pytest.raises(PostNotEditableError):
        EditPostUseCase(_repo()).fill_experience(99, ExperienceResult.WORKED, ["예"], "")
