"""Post entity tests — 15+ tests for state machine."""
from datetime import datetime

import pytest

from src.domain.entities.post import Post
from src.domain.exceptions import InvalidStatusTransitionError
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus


class TestPostCreation:
    def test_create_with_defaults(self):
        post = Post(row_index=2, keyword="SSO란")
        assert post.row_index == 2
        assert post.keyword == "SSO란"
        assert post.status == PostStatus.PENDING
        assert post.content is None

    def test_create_with_content(self):
        content = PostContent(title="제목", body_markdown="본문")
        post = Post(row_index=3, keyword="제로 트러스트", content=content)
        assert post.content.title == "제목"


class TestMarkPublishing:
    def test_pending_to_publishing(self):
        post = Post(row_index=1, keyword="test")
        post.mark_publishing()
        assert post.status == PostStatus.PUBLISHING

    def test_non_pending_raises(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.PUBLISHED)
        with pytest.raises(InvalidStatusTransitionError):
            post.mark_publishing()

    def test_from_failed_raises(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.FAILED)
        with pytest.raises(InvalidStatusTransitionError):
            post.mark_publishing()

    def test_from_waiting_raises(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.WAITING)
        with pytest.raises(InvalidStatusTransitionError):
            post.mark_publishing()


class TestMarkPublished:
    def test_records_url_and_time(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.PUBLISHING)
        post.mark_published("https://blog.tistory.com/123")
        assert post.status == PostStatus.PUBLISHED
        assert post.published_url == "https://blog.tistory.com/123"
        assert isinstance(post.published_at, datetime)


class TestMarkFailed:
    def test_records_error(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.PUBLISHING)
        post.mark_failed("셀렉터 실패")
        assert post.status == PostStatus.FAILED
        assert post.error_message == "셀렉터 실패"

    def test_truncates_reason_to_200(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.PUBLISHING)
        long_reason = "x" * 500
        post.mark_failed(long_reason)
        assert len(post.error_message) == 200


class TestResetToPending:
    def test_publishing_to_pending(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.PUBLISHING)
        post.reset_to_pending()
        assert post.status == PostStatus.PENDING
        assert "자동 복구" in post.error_message

    def test_non_publishing_does_nothing(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.FAILED)
        post.reset_to_pending()
        assert post.status == PostStatus.FAILED  # unchanged


class TestIsPublishable:
    def test_true_when_pending_with_body(self):
        content = PostContent(title="제목", body_markdown="본문 있음")
        post = Post(row_index=1, keyword="test", content=content)
        assert post.is_publishable() is True

    def test_false_when_not_pending(self):
        content = PostContent(title="제목", body_markdown="본문")
        post = Post(row_index=1, keyword="test", content=content, status=PostStatus.PUBLISHED)
        assert post.is_publishable() is False

    def test_false_when_no_content(self):
        post = Post(row_index=1, keyword="test")
        assert post.is_publishable() is False

    def test_false_when_body_empty(self):
        content = PostContent(title="제목", body_markdown="")
        post = Post(row_index=1, keyword="test", content=content)
        assert post.is_publishable() is False
