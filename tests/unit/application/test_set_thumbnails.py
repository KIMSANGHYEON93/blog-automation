"""Unit tests for SetThumbnailsUseCase."""
from __future__ import annotations

from src.application.use_cases.set_thumbnails import SetThumbnailsUseCase
from src.domain.entities.post import Post
from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.image_generation_port import ImageGenerationPort
from src.domain.value_objects.image_prompt import ImagePrompt
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.domain.value_objects.publish_result import PublishResult
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


class MockImageGenerator(ImageGenerationPort):
    def __init__(self, url: str = "https://img.example.com/thumb.png", fail: bool = False):
        self._url = url
        self._fail = fail
        self.call_count = 0

    def generate(self, prompt: ImagePrompt) -> str:
        self.call_count += 1
        if self._fail:
            raise RuntimeError("DALL-E API error")
        return self._url


class MockBrowser(BrowserPort):
    """BrowserPort mock — update()만 사용."""

    def __init__(self, update_success: bool = True):
        self._update_success = update_success
        self.updates: list[Post] = []

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def login(self) -> bool:
        return True

    def publish(self, post: Post) -> PublishResult:
        return PublishResult.fail("not implemented in mock")

    def update(self, post: Post) -> PublishResult:
        self.updates.append(post)
        if self._update_success:
            return PublishResult.ok(
                post.published_url, entry_id=post.entry_id,
            )
        return PublishResult.fail("API 수정 실패")


def _make_published_post(
    row_index: int, keyword: str, entry_id: str = "100",
    thumbnail_url: str = "",
) -> Post:
    post = Post(
        row_index=row_index,
        keyword=keyword,
        category="가이드",
        status=PostStatus.PUBLISHED,
        published_url=f"https://test.tistory.com/{entry_id}",
        entry_id=entry_id,
        content=PostContent(
            title=f"{keyword} 가이드",
            body_markdown="x" * 3000,
            thumbnail_url=thumbnail_url,
        ),
    )
    return post


class TestSetThumbnailsNormal:
    def test_generates_and_updates_thumbnail(self):
        post = _make_published_post(2, "Docker", entry_id="200")
        repo = InMemoryPostRepository([post])
        gen = MockImageGenerator()
        browser = MockBrowser()

        uc = SetThumbnailsUseCase(repo=repo, image_gen=gen, browser=browser)
        stats = uc.execute()

        assert stats.generated == 1
        assert stats.uploaded == 1
        assert stats.failed == 0
        assert gen.call_count == 1
        assert len(browser.updates) == 1
        # update()에 전달된 Post의 thumbnail_url이 설정되어 있어야 함
        updated_post = browser.updates[0]
        assert updated_post.content is not None
        assert updated_post.content.thumbnail_url == "https://img.example.com/thumb.png"
        assert updated_post.entry_id == "200"

    def test_skips_posts_with_existing_thumbnail(self):
        post = _make_published_post(
            2, "Docker", entry_id="200", thumbnail_url="https://existing.jpg",
        )
        repo = InMemoryPostRepository([post])
        gen = MockImageGenerator()
        browser = MockBrowser()

        uc = SetThumbnailsUseCase(repo=repo, image_gen=gen, browser=browser)
        stats = uc.execute()

        assert stats.total == 0
        assert gen.call_count == 0

    def test_skips_posts_without_entry_id(self):
        post = _make_published_post(2, "Docker", entry_id="")
        repo = InMemoryPostRepository([post])
        gen = MockImageGenerator()
        browser = MockBrowser()

        uc = SetThumbnailsUseCase(repo=repo, image_gen=gen, browser=browser)
        stats = uc.execute()

        assert stats.total == 0

    def test_max_posts_limit(self):
        posts = [
            _make_published_post(i, f"kw{i}", entry_id=str(100 + i))
            for i in range(10)
        ]
        repo = InMemoryPostRepository(posts)
        gen = MockImageGenerator()
        browser = MockBrowser()

        uc = SetThumbnailsUseCase(
            repo=repo, image_gen=gen, browser=browser, max_posts=3,
        )
        stats = uc.execute()

        assert stats.total == 10
        assert stats.generated == 3
        assert gen.call_count == 3


class TestSetThumbnailsFailures:
    def test_image_generation_failure(self):
        post = _make_published_post(2, "Docker", entry_id="200")
        repo = InMemoryPostRepository([post])
        gen = MockImageGenerator(fail=True)
        browser = MockBrowser()

        uc = SetThumbnailsUseCase(repo=repo, image_gen=gen, browser=browser)
        stats = uc.execute()

        assert stats.generated == 0
        assert stats.failed == 1
        assert len(browser.updates) == 0

    def test_update_failure(self):
        post = _make_published_post(2, "Docker", entry_id="200")
        repo = InMemoryPostRepository([post])
        gen = MockImageGenerator()
        browser = MockBrowser(update_success=False)

        uc = SetThumbnailsUseCase(repo=repo, image_gen=gen, browser=browser)
        stats = uc.execute()

        assert stats.generated == 1
        assert stats.uploaded == 0
        assert stats.failed == 1

    def test_saves_thumbnail_url_to_repo(self):
        post = _make_published_post(2, "Docker", entry_id="200")
        repo = InMemoryPostRepository([post])
        gen = MockImageGenerator(url="https://dalle.img/new.png")
        browser = MockBrowser()

        uc = SetThumbnailsUseCase(repo=repo, image_gen=gen, browser=browser)
        uc.execute()

        saved = repo.all()[0]
        assert saved.content is not None
        assert saved.content.thumbnail_url == "https://dalle.img/new.png"

    def test_empty_published_list(self):
        repo = InMemoryPostRepository([])
        gen = MockImageGenerator()
        browser = MockBrowser()

        uc = SetThumbnailsUseCase(repo=repo, image_gen=gen, browser=browser)
        stats = uc.execute()

        assert stats.total == 0
        assert stats.generated == 0
