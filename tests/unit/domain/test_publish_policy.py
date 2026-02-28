"""PublishPolicy domain service tests."""
from src.domain.entities.post import Post
from src.domain.services.publish_policy import PublishPolicy
from src.domain.value_objects.post_content import PostContent


def _make_publishable_post(idx: int) -> Post:
    return Post(
        row_index=idx,
        keyword=f"keyword_{idx}",
        content=PostContent(title=f"Title {idx}", body_markdown="Body content"),
    )


def _make_unpublishable_post(idx: int) -> Post:
    return Post(row_index=idx, keyword=f"keyword_{idx}")


class TestPublishPolicy:
    def test_filter_publishable_returns_only_eligible(self):
        policy = PublishPolicy(max_posts=5)
        posts = [
            _make_publishable_post(1),
            _make_unpublishable_post(2),
            _make_publishable_post(3),
        ]
        result = policy.filter_publishable(posts)
        assert len(result) == 2
        assert result[0].row_index == 1
        assert result[1].row_index == 3

    def test_filter_respects_max_posts(self):
        policy = PublishPolicy(max_posts=2)
        posts = [_make_publishable_post(i) for i in range(5)]
        result = policy.filter_publishable(posts)
        assert len(result) == 2

    def test_filter_empty_list(self):
        policy = PublishPolicy()
        assert policy.filter_publishable([]) == []

    def test_should_continue_under_threshold(self):
        policy = PublishPolicy()
        assert policy.should_continue_after_failure(0) is True
        assert policy.should_continue_after_failure(2) is True

    def test_should_stop_at_threshold(self):
        policy = PublishPolicy()
        assert policy.should_continue_after_failure(3) is False
        assert policy.should_continue_after_failure(5) is False
