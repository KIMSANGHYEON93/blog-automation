"""BrowserPort — Port interface for browser automation (defined by Domain)."""
from abc import ABC, abstractmethod

from src.domain.entities.post import Post
from src.domain.value_objects.publish_result import PublishResult


class BrowserPort(ABC):
    @abstractmethod
    def start(self) -> None:
        """Start browser instance."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop browser and release resources."""
        ...

    @abstractmethod
    def login(self) -> bool:
        """Authenticate. Returns True on success."""
        ...

    @abstractmethod
    def publish(self, post: Post) -> PublishResult:
        """Publish a single post. Returns PublishResult."""
        ...
