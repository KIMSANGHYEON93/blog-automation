"""Post entity tests — 25+ tests for state machine."""
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


class TestResetFailedToPending:
    def test_failed_to_pending(self):
        post = Post(row_index=12, keyword="Jenkins vs GitHub Actions", status=PostStatus.FAILED,
                    error_message="이전 UI 버튼 코드 실패")
        post.reset_failed_to_pending()
        assert post.status == PostStatus.PENDING
        assert post.error_message == ""

    def test_non_failed_raises(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.PUBLISHED)
        with pytest.raises(InvalidStatusTransitionError):
            post.reset_failed_to_pending()

    def test_clears_error_message(self):
        post = Post(row_index=5, keyword="test", status=PostStatus.FAILED,
                    error_message="셀렉터 미발견으로 인한 실패")
        post.reset_failed_to_pending()
        assert post.error_message == ""
        assert post.status == PostStatus.PENDING


class TestIsPublishable:
    def test_true_when_pending_with_body(self):
        content = PostContent(title="제목", body_markdown="x" * 3000)
        post = Post(row_index=1, keyword="test", content=content, quality_score=80)
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

    def test_false_when_quality_score_below_70(self):
        content = PostContent(title="제목", body_markdown="본문 있음")
        post = Post(row_index=1, keyword="test", content=content, quality_score=50)
        assert post.is_publishable() is False

    def test_true_when_quality_score_at_least_70(self):
        content = PostContent(title="제목", body_markdown="x" * 3000)
        post = Post(row_index=1, keyword="test", content=content, quality_score=70)
        assert post.is_publishable() is True

    def test_false_when_content_too_short(self):
        short_body = "x" * 2999  # Just under 3000
        content = PostContent(title="Title", body_markdown=short_body)
        post = Post(row_index=1, keyword="test", content=content, quality_score=80)
        assert post.is_publishable() is False

    def test_true_when_content_sufficient_length(self):
        long_body = "x" * 3000  # Exactly 3000
        content = PostContent(title="Title", body_markdown=long_body)
        post = Post(row_index=1, keyword="test", content=content, quality_score=80)
        assert post.is_publishable() is True


class TestMarkRevisionPending:
    def test_published_to_revision_pending(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.PUBLISHED)
        post.mark_revision_pending("본문 짧음")
        assert post.status == PostStatus.REVISION_PENDING
        assert post.error_message == "본문 짧음"

    def test_non_published_raises(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.PENDING)
        with pytest.raises(InvalidStatusTransitionError):
            post.mark_revision_pending("이유")

    def test_empty_reason(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.PUBLISHED)
        post.mark_revision_pending()
        assert post.status == PostStatus.REVISION_PENDING
        assert post.error_message == ""

    def test_truncates_reason_to_200(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.PUBLISHED)
        post.mark_revision_pending("x" * 500)
        assert len(post.error_message) == 200


class TestMarkRevising:
    def test_revision_pending_to_revising(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.REVISION_PENDING)
        post.mark_revising()
        assert post.status == PostStatus.REVISING

    def test_non_revision_pending_raises(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.PUBLISHED)
        with pytest.raises(InvalidStatusTransitionError):
            post.mark_revising()


class TestMarkRevised:
    def test_revising_to_published(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.REVISING)
        post.mark_revised("https://blog.tistory.com/123")
        assert post.status == PostStatus.PUBLISHED
        assert post.published_url == "https://blog.tistory.com/123"
        assert isinstance(post.published_at, datetime)

    def test_non_revising_raises(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.PUBLISHED)
        with pytest.raises(InvalidStatusTransitionError):
            post.mark_revised("https://blog.tistory.com/123")


class TestResetRevisingToRevisionPending:
    def test_revising_to_revision_pending(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.REVISING)
        post.reset_revising_to_revision_pending()
        assert post.status == PostStatus.REVISION_PENDING
        assert "자동 복구" in post.error_message

    def test_non_revising_does_nothing(self):
        post = Post(row_index=1, keyword="test", status=PostStatus.FAILED)
        post.reset_revising_to_revision_pending()
        assert post.status == PostStatus.FAILED


class TestIsRevisable:
    def test_true_when_revision_pending_with_body_and_entry_id(self):
        content = PostContent(title="제목", body_markdown="본문 있음")
        post = Post(row_index=1, keyword="test", content=content,
                    status=PostStatus.REVISION_PENDING, entry_id="123")
        assert post.is_revisable() is True

    def test_false_when_not_revision_pending(self):
        content = PostContent(title="제목", body_markdown="본문")
        post = Post(row_index=1, keyword="test", content=content,
                    status=PostStatus.PUBLISHED, entry_id="123")
        assert post.is_revisable() is False

    def test_false_when_no_content(self):
        post = Post(row_index=1, keyword="test",
                    status=PostStatus.REVISION_PENDING, entry_id="123")
        assert post.is_revisable() is False

    def test_false_when_body_empty(self):
        content = PostContent(title="제목", body_markdown="")
        post = Post(row_index=1, keyword="test", content=content,
                    status=PostStatus.REVISION_PENDING, entry_id="123")
        assert post.is_revisable() is False

    def test_false_when_no_entry_id(self):
        content = PostContent(title="제목", body_markdown="본문 있음")
        post = Post(row_index=1, keyword="test", content=content,
                    status=PostStatus.REVISION_PENDING, entry_id="")
        assert post.is_revisable() is False


class TestInternalLinkKeywords:
    def test_default_empty_list(self):
        post = Post(row_index=1, keyword="test")
        assert post.internal_link_keywords == []

    def test_create_with_keywords(self):
        post = Post(
            row_index=1, keyword="SSO란",
            internal_link_keywords=["LDAP", "OAuth", "SAML"],
        )
        assert post.internal_link_keywords == ["LDAP", "OAuth", "SAML"]
        assert len(post.internal_link_keywords) == 3
