"""MockBrowserAdapter — Test double for unit tests. No external dependencies."""
from src.domain.entities.post import Post
from src.domain.ports.browser_port import BrowserPort
from src.domain.value_objects.publish_result import PublishResult


class MockBrowserAdapter(BrowserPort):
    """단위 테스트용 Mock 브라우저. 외부 서비스 불필요."""

    def __init__(self, login_success: bool = True,
                 publish_url: str = "https://test.tistory.com/1",
                 publish_error: str = ""):
        self._login_success = login_success
        self._publish_url = publish_url
        self._publish_error = publish_error
        self.started = False
        self.stopped = False
        self.logged_in = False
        self.published_posts: list = []

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def login(self) -> bool:
        self.logged_in = self._login_success
        return self._login_success

    def publish(self, post: Post) -> PublishResult:
        self.published_posts.append(post)
        if self._publish_error:
            return PublishResult.fail(self._publish_error)
        return PublishResult.ok(self._publish_url)
