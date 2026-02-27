"""Domain exceptions tests."""
import pytest

from src.domain.exceptions import (
    DomainError,
    InvalidStatusTransition,
    PostNotPublishable,
    ContentMissing,
)
from src.domain.value_objects.post_status import PostStatus


class TestDomainExceptions:
    def test_domain_error_is_exception(self):
        assert issubclass(DomainError, Exception)

    def test_invalid_status_transition(self):
        err = InvalidStatusTransition(PostStatus.PUBLISHED, PostStatus.PUBLISHING)
        assert "발행완료" in str(err)
        assert "발행중" in str(err)
        assert err.current_status == PostStatus.PUBLISHED
        assert err.target_status == PostStatus.PUBLISHING

    def test_post_not_publishable(self):
        err = PostNotPublishable("이유")
        assert isinstance(err, DomainError)

    def test_content_missing(self):
        err = ContentMissing("본문 없음")
        assert isinstance(err, DomainError)
