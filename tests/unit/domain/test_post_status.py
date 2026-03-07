"""PostStatus value object tests — TDD RED phase."""
import pytest

from src.domain.value_objects.post_status import PostStatus


class TestPostStatus:
    """PostStatus Enum should have exactly 9 states."""

    def test_has_nine_states(self):
        assert len(PostStatus) == 9

    def test_waiting_state(self):
        assert PostStatus.WAITING.value == "대기"

    def test_generating_state(self):
        assert PostStatus.GENERATING.value == "생성중"

    def test_pending_state(self):
        assert PostStatus.PENDING.value == "발행대기"

    def test_publishing_state(self):
        assert PostStatus.PUBLISHING.value == "발행중"

    def test_published_state(self):
        assert PostStatus.PUBLISHED.value == "발행완료"

    def test_failed_state(self):
        assert PostStatus.FAILED.value == "발행실패"

    def test_hold_state(self):
        assert PostStatus.HOLD.value == "보류"

    def test_from_string_valid(self):
        assert PostStatus.from_string("발행대기") == PostStatus.PENDING

    def test_revision_pending_state(self):
        assert PostStatus.REVISION_PENDING.value == "수정대기"

    def test_revising_state(self):
        assert PostStatus.REVISING.value == "수정중"

    def test_from_string_revision_pending(self):
        assert PostStatus.from_string("수정대기") == PostStatus.REVISION_PENDING

    def test_from_string_revising(self):
        assert PostStatus.from_string("수정중") == PostStatus.REVISING

    def test_from_string_invalid_raises(self):
        with pytest.raises(ValueError):
            PostStatus.from_string("존재하지않는상태")
