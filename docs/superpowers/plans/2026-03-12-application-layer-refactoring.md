# Application Layer Refactoring Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract duplicated internal link enrichment logic from PublishPostsUseCase and RevisePostsUseCase into a shared Application Service, and convert direct Domain Service instantiation to constructor injection.

**Architecture:** The refactoring follows DDD 4-Layer rules (Interface → Application → Domain ← Infrastructure). A new `InternalLinkEnricher` Application Service extracts ~40 lines of duplicated code from two Use Cases. Domain Services (`PublishPolicy`, `QuotaManager`) move from internal instantiation to constructor injection, improving testability without changing any interfaces.

**Tech Stack:** Python 3.9+, pytest, ruff, mypy

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/application/services/__init__.py` | Create (empty) | Package marker |
| `src/application/services/internal_link_enricher.py` | Create | Shared Application Service: enriches posts with related links HTML and keyword→URL maps |
| `src/application/use_cases/publish_posts.py` | Modify | Remove duplicated link methods, accept enricher/policy/quota via constructor |
| `src/application/use_cases/revise_posts.py` | Modify | Remove duplicated link methods, accept enricher via constructor |
| `src/interface/cli.py` | Modify | Assemble new dependencies at Composition Root |
| `tests/unit/application/test_internal_link_enricher.py` | Create | Unit tests for InternalLinkEnricher |
| `tests/unit/application/test_publish_posts_usecase.py` | Modify | Update DI in test factories |
| `tests/unit/application/test_revise_posts_usecase.py` | Modify | Update DI in test factories |

---

## Chunk 1: InternalLinkEnricher Service

### Task 1: Create InternalLinkEnricher with tests (TDD)

**Files:**
- Create: `src/application/services/__init__.py`
- Create: `src/application/services/internal_link_enricher.py`
- Create: `tests/unit/application/test_internal_link_enricher.py`

**Context:** Two Use Cases have identical methods for:
1. `_enrich_with_related_links()` — selects related posts via `InternalLinkService.select_links()`, builds an HTML block, appends to `post.content.body_markdown`
2. `_attach_internal_link_map()` — builds a `keyword→published_url` dict from published posts, assigns to `post.internal_link_map`
3. Both also call `self._link_service.identify_hubs(published_posts)` in their `execute()` methods

This task extracts all three into a new class.

- [ ] **Step 1: Write failing tests for InternalLinkEnricher**

```python
# tests/unit/application/test_internal_link_enricher.py
"""Unit tests for InternalLinkEnricher — Application Service."""
from __future__ import annotations

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.domain.entities.post import Post
from src.domain.services.internal_link_service import InternalLinkService
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus


def _make_published(row: int, keyword: str, url: str,
                    category: str = "IT",
                    link_kws: list[str] | None = None) -> Post:
    return Post(
        row_index=row,
        keyword=keyword,
        category=category,
        status=PostStatus.PUBLISHED,
        content=PostContent(title=keyword, body_markdown="본문"),
        published_url=url,
        internal_link_keywords=link_kws or [],
    )


def _make_pending(row: int, keyword: str, category: str = "IT",
                  body: str = "## 내용\n본문") -> Post:
    return Post(
        row_index=row,
        keyword=keyword,
        category=category,
        status=PostStatus.PENDING,
        content=PostContent(title=keyword, body_markdown=body),
    )


class TestEnrichWithRelatedLinks:
    """enrich_with_related_links() 테스트."""

    def test_관련_글_HTML_삽입(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        post = _make_pending(10, "AD란")
        pub1 = _make_published(1, "SSO란", "https://test.tistory.com/1")
        pub2 = _make_published(2, "LDAP란", "https://test.tistory.com/2")
        hubs = enricher.identify_hubs([pub1, pub2])

        enricher.enrich_with_related_links(post, [pub1, pub2], hubs)

        assert "관련 글" in post.content.body_markdown
        assert "SSO란" in post.content.body_markdown

    def test_content_None이면_무시(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        post = Post(row_index=10, keyword="AD란", status=PostStatus.PENDING)

        enricher.enrich_with_related_links(post, [], [])
        # No exception, no change
        assert post.content is None

    def test_빈_본문이면_무시(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        post = Post(
            row_index=10, keyword="AD란", status=PostStatus.PENDING,
            content=PostContent(title="AD란", body_markdown=""),
        )

        enricher.enrich_with_related_links(post, [], [])
        assert post.content.body_markdown == ""

    def test_발행글_없으면_관련글_미삽입(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        post = _make_pending(10, "AD란")

        enricher.enrich_with_related_links(post, [], [])

        assert "관련 글" not in post.content.body_markdown


class TestAttachInternalLinkMap:
    """attach_internal_link_map() 테스트."""

    def test_keyword_URL_매핑_첨부(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        post = _make_pending(10, "AD란")
        pub1 = _make_published(1, "SSO란", "https://test.tistory.com/1")
        pub2 = _make_published(2, "LDAP란", "https://test.tistory.com/2")

        enricher.attach_internal_link_map(post, [pub1, pub2])

        assert post.internal_link_map == {
            "SSO란": "https://test.tistory.com/1",
            "LDAP란": "https://test.tistory.com/2",
        }

    def test_자기자신_제외(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        post = _make_pending(1, "AD란")
        pub_self = _make_published(1, "AD란", "https://test.tistory.com/1")
        pub_other = _make_published(2, "SSO란", "https://test.tistory.com/2")

        enricher.attach_internal_link_map(post, [pub_self, pub_other])

        assert "AD란" not in post.internal_link_map
        assert "SSO란" in post.internal_link_map

    def test_content_None이면_무시(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        post = Post(row_index=10, keyword="AD란", status=PostStatus.PENDING)

        enricher.attach_internal_link_map(post, [])
        assert post.internal_link_map is None


class TestIdentifyHubs:
    """identify_hubs() 위임 테스트."""

    def test_허브_식별_위임(self):
        enricher = InternalLinkEnricher(InternalLinkService())
        pub1 = _make_published(1, "SSO란", "https://test.tistory.com/1")
        pub2 = _make_published(
            2, "LDAP란", "https://test.tistory.com/2",
            link_kws=["SSO"],
        )
        pub3 = _make_published(
            3, "AD란", "https://test.tistory.com/3",
            link_kws=["SSO"],
        )

        hubs = enricher.identify_hubs([pub1, pub2, pub3])

        hub_keywords = [h.keyword for h in hubs]
        assert "SSO란" in hub_keywords
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/application/test_internal_link_enricher.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.application.services'`

- [ ] **Step 3: Create package and implement InternalLinkEnricher**

```python
# src/application/services/__init__.py
# (empty — package marker)
```

```python
# src/application/services/internal_link_enricher.py
"""InternalLinkEnricher — shared Application Service for internal link enrichment."""
from __future__ import annotations

from dataclasses import replace

from src.domain.entities.post import Post
from src.domain.services.internal_link_service import InternalLinkService


class InternalLinkEnricher:
    """발행/수정 시 공통으로 사용하는 내부 링크 강화 서비스.

    InternalLinkService(Domain)를 주입받아, 관련 글 HTML 생성과
    keyword→URL 매핑을 post에 첨부한다.
    """

    def __init__(self, link_service: InternalLinkService) -> None:
        self._link_service = link_service

    def identify_hubs(self, published: list[Post]) -> list[Post]:
        """Hub post 식별을 InternalLinkService에 위임."""
        return self._link_service.identify_hubs(published)

    def enrich_with_related_links(
        self, post: Post, published: list[Post], hubs: list[Post],
    ) -> None:
        """관련 글 HTML을 본문 끝에 추가."""
        if not post.content or not post.content.has_body():
            return

        related = self._link_service.select_links(post, published, hubs)
        if not related:
            return

        items = "".join(
            f'<li style="margin:8px 0;">'
            f'<a href="{p.published_url}">{p.keyword}</a></li>'
            for p in related[:5]
        )
        html = (
            "\n\n<hr>\n"
            '<div style="margin-top:30px;padding:20px;'
            'background:#f8f9fa;border-radius:8px;">'
            "<h3>관련 글</h3>"
            f'<ul style="list-style:none;padding:0;">{items}</ul>'
            "</div>"
        )
        post.content = replace(
            post.content,
            body_markdown=(post.content.body_markdown or "") + html,
        )

    def attach_internal_link_map(
        self, post: Post, published: list[Post],
    ) -> None:
        """발행 완료 포스트의 keyword→URL 매핑을 post에 첨부.

        tistory_editor가 HTML 변환 후 inject_internal_links()에 전달.
        """
        if not post.content or not post.content.has_body():
            return
        link_map = {
            p.keyword: p.published_url
            for p in published
            if p.keyword and p.published_url
            and p.row_index != post.row_index
        }
        if link_map:
            post.internal_link_map = link_map
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/application/test_internal_link_enricher.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Run lint + typecheck**

Run: `ruff check src/application/services/ tests/unit/application/test_internal_link_enricher.py && python3 -m mypy src/application/services/ --ignore-missing-imports`
Expected: 0 issues

- [ ] **Step 6: Commit**

```bash
git add src/application/services/__init__.py src/application/services/internal_link_enricher.py tests/unit/application/test_internal_link_enricher.py
git commit -m "feat(app): extract InternalLinkEnricher application service

Extracts duplicated _enrich_with_related_links() and
_attach_internal_link_map() into a shared service with tests."
```

---

## Chunk 2: Refactor PublishPostsUseCase

### Task 2: Refactor PublishPostsUseCase to use DI

**Files:**
- Modify: `src/application/use_cases/publish_posts.py`
- Modify: `tests/unit/application/test_publish_posts_usecase.py`

**Context:** Currently `PublishPostsUseCase.__init__()` (lines 24-31) directly instantiates `InternalLinkService()`, `PublishPolicy()`, and `QuotaManager()`. After refactoring:
- Remove `_enrich_with_related_links()` (lines 93-118) and `_attach_internal_link_map()` (lines 120-136)
- Accept `InternalLinkEnricher`, `PublishPolicy`, and `QuotaManager` via constructor
- Replace `self._link_service.identify_hubs()` with `self._enricher.identify_hubs()`
- Replace `self._enrich_with_related_links()` with `self._enricher.enrich_with_related_links()`
- Replace `self._attach_internal_link_map()` with `self._enricher.attach_internal_link_map()`

- [ ] **Step 1: Update test file to use new DI constructor**

In `tests/unit/application/test_publish_posts_usecase.py`, add imports and update every `PublishPostsUseCase(...)` call. The test file must be updated first because TDD convention means tests express the desired API.

Add these imports at the top (after existing imports):

```python
from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.domain.services.internal_link_service import InternalLinkService
from src.domain.services.publish_policy import PublishPolicy
from src.domain.services.quota_manager import QuotaManager
```

Add a helper function after `make_publishable_post()`:

```python
def make_use_case(repo, browser, max_posts=5):
    """Factory for PublishPostsUseCase with fully-injected dependencies."""
    link_service = InternalLinkService()
    enricher = InternalLinkEnricher(link_service)
    policy = PublishPolicy(max_posts=max_posts)
    quota = QuotaManager()
    return PublishPostsUseCase(
        repo=repo, browser=browser,
        enricher=enricher, policy=policy, quota=quota,
        max_posts=max_posts,
    )
```

Then replace every occurrence of:
```python
PublishPostsUseCase(repo=repo, browser=browser)
```
with:
```python
make_use_case(repo, browser)
```

And every occurrence of:
```python
PublishPostsUseCase(repo=repo, browser=browser, max_posts=5)
```
with:
```python
make_use_case(repo, browser, max_posts=5)
```

Specifically, these lines in the test file need updating (all `PublishPostsUseCase(...)` calls):
- `TestPublishPostsNormalFlow.test_2건_정상_발행` (line 32)
- `TestPublishPostsNormalFlow.test_발행_후_상태_PUBLISHED` (line 44)
- `TestPublishPostsSkip.test_본문_없는_포스트_건너뛰기` (line 65)
- `TestPublishPostsSkip.test_content_None_건너뛰기` (line 76)
- `TestPublishPostsFailure.test_발행_실패_시_FAILED_상태` (line 90)
- `TestPublishPostsFailure.test_로그인_실패_즉시_중단` (line 103)
- `TestPublishPostsBrowserLifecycle.test_예외_발생_시_브라우저_종료` (line 123)
- `TestPublishPostsBrowserLifecycle.test_빈_목록일_때_브라우저_미시작` (line 132)
- `TestPublishPostsDailyLimit.test_일일_제한_시_나머지_건너뛰기` (line 159)
- `TestPublishPostsDailyLimit.test_일일_제한_포스트_발행대기_복원` (line 181)
- `TestRelatedLinks.test_관련_글_삽입_동일_카테고리` (line 225)
- `TestRelatedLinks.test_관련_글_미삽입_발행글_없음` (line 246)
- `TestRelatedLinks.test_관련_글_자기자신_제외` (line 269)
- `TestHubSpokeLinks.test_허브_글이_관련_글에서_우선_링크됨` (line 321)
- `TestHubSpokeLinks.test_키워드_없는_글은_카테고리_폴백` (line 345)
- `TestHubSpokeLinks.test_키워드_겹침_기반_우선순위` (line 372)

- [ ] **Step 2: Run tests to verify they fail (old constructor doesn't match)**

Run: `python3 -m pytest tests/unit/application/test_publish_posts_usecase.py -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'enricher'`

- [ ] **Step 3: Refactor PublishPostsUseCase implementation**

Replace the entire file `src/application/use_cases/publish_posts.py` with:

```python
"""PublishPostsUseCase — Orchestrates the blog post publishing workflow."""
import logging
from dataclasses import dataclass

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.domain.entities.post import Post
from src.domain.exceptions import DailyPublishLimitError
from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.post_repository import PostRepository
from src.domain.services.publish_policy import PublishPolicy
from src.domain.services.quota_manager import QuotaManager

logger = logging.getLogger(__name__)


@dataclass
class PublishStats:
    published: int = 0
    failed: int = 0
    skipped: int = 0


class PublishPostsUseCase:
    def __init__(
        self,
        repo: PostRepository,
        browser: BrowserPort,
        enricher: InternalLinkEnricher,
        policy: PublishPolicy,
        quota: QuotaManager,
        max_posts: int = 5,
    ):
        self._repo = repo
        self._browser = browser
        self._enricher = enricher
        self._policy = policy
        self._quota = quota
        self._max_posts = max_posts

    def execute(self) -> PublishStats:
        stats = PublishStats()
        posts = self._repo.find_pending(limit=self._max_posts)

        if not posts:
            logger.info("발행 대기 포스트 없음")
            return stats

        # PublishPolicy로 발행 가능한 포스트만 필터링
        publishable = self._policy.filter_publishable(posts)
        stats.skipped = len(posts) - len(publishable)

        if not publishable:
            logger.info("발행 가능한 포스트 없음 (필터링 후)")
            return stats

        # 쿼터 사전 체크
        published_today = self._repo.count_published_today()
        if not self._quota.can_publish(published_today):
            logger.warning("일일 발행 쿼터 소진 — 발행 건너뜀")
            return stats

        published_posts = self._repo.find_published(limit=50)
        hubs = self._enricher.identify_hubs(published_posts)

        self._browser.start()
        try:
            if not self._browser.login():
                logger.error("로그인 실패 — 발행 중단")
                return stats

            consecutive_failures = 0
            for post in publishable:
                if not self._policy.should_continue_after_failure(
                    consecutive_failures,
                ):
                    logger.warning(
                        f"연속 실패 {consecutive_failures}회 — 발행 중단"
                    )
                    break

                self._enricher.enrich_with_related_links(
                    post, published_posts, hubs,
                )
                self._enricher.attach_internal_link_map(post, published_posts)
                prev_failed = stats.failed
                try:
                    self._publish_single(post, stats)
                    if stats.failed > prev_failed:
                        consecutive_failures += 1
                    else:
                        consecutive_failures = 0
                except DailyPublishLimitError:
                    logger.warning(
                        "일일 발행 제한 도달 — 나머지 포스트 건너뜀 "
                        f"(발행: {stats.published}, 실패: {stats.failed})"
                    )
                    break

        finally:
            self._browser.stop()

        return stats

    def _publish_single(self, post: Post, stats: PublishStats) -> None:
        if not post.is_publishable():
            logger.warning(f"발행 불가 포스트 건너뜀: row={post.row_index}")
            stats.skipped += 1
            return

        try:
            post.mark_publishing()
            self._repo.save(post)

            result = self._browser.publish(post)

            if result.success:
                post.mark_published(result.url, entry_id=result.entry_id)
                stats.published += 1
                logger.info(f"발행 완료: {post.keyword} → {result.url}")
            else:
                post.mark_failed(result.error)
                stats.failed += 1
                logger.error(f"발행 실패: {post.keyword} — {result.error}")

        except DailyPublishLimitError:
            post.reset_to_pending()  # 일일 제한 시 발행대기로 복원
            self._repo.save(post)
            raise
        except Exception as e:
            post.mark_failed(str(e))
            stats.failed += 1
            logger.exception(f"발행 중 예외: {post.keyword}")
        finally:
            self._repo.save(post)
```

Key changes from the original:
- Removed `from dataclasses import replace` (no longer needed)
- Removed `from src.domain.services.internal_link_service import InternalLinkService`
- Added `from src.application.services.internal_link_enricher import InternalLinkEnricher`
- Retained `from src.domain.entities.post import Post` for `_publish_single` type annotation
- Constructor now accepts `enricher`, `policy`, `quota` as parameters
- `_enrich_with_related_links()` method deleted — calls `self._enricher.enrich_with_related_links()`
- `_attach_internal_link_map()` method deleted — calls `self._enricher.attach_internal_link_map()`
- `self._link_service.identify_hubs()` → `self._enricher.identify_hubs()`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/application/test_publish_posts_usecase.py -v`
Expected: All 16 tests PASS

- [ ] **Step 5: Run full test suite to check nothing else broke**

Run: `python3 -m pytest tests/unit/ -v --tb=short`
Expected: All ~423 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/application/use_cases/publish_posts.py tests/unit/application/test_publish_posts_usecase.py
git commit -m "refactor(app): PublishPostsUseCase uses DI for enricher/policy/quota

Removes duplicated _enrich_with_related_links and _attach_internal_link_map.
Domain services now injected via constructor instead of direct instantiation."
```

---

## Chunk 3: Refactor RevisePostsUseCase + CLI

### Task 3: Refactor RevisePostsUseCase to use DI

**Files:**
- Modify: `src/application/use_cases/revise_posts.py`
- Modify: `tests/unit/application/test_revise_posts_usecase.py`

**Context:** Same pattern as Task 2 but for RevisePostsUseCase. This use case only uses `InternalLinkService` (no `PublishPolicy` or `QuotaManager`), so it only needs `InternalLinkEnricher`.

- [ ] **Step 1: Update test file to use new DI constructor**

In `tests/unit/application/test_revise_posts_usecase.py`, add imports:

```python
from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.domain.services.internal_link_service import InternalLinkService
```

Add a helper function after `make_revisable_post()`:

```python
def make_use_case(repo, browser, max_posts=5):
    """Factory for RevisePostsUseCase with fully-injected dependencies."""
    enricher = InternalLinkEnricher(InternalLinkService())
    return RevisePostsUseCase(
        repo=repo, browser=browser,
        enricher=enricher,
        max_posts=max_posts,
    )
```

Then replace every occurrence of:
```python
RevisePostsUseCase(repo=repo, browser=browser)
```
with:
```python
make_use_case(repo, browser)
```

And:
```python
RevisePostsUseCase(repo=repo, browser=browser, max_posts=5)
```
with:
```python
make_use_case(repo, browser, max_posts=5)
```

Specifically, these lines need updating:
- `TestRevisePostsNormalFlow.test_2건_정상_수정` (line 35)
- `TestRevisePostsNormalFlow.test_수정_후_상태_PUBLISHED` (line 47)
- `TestRevisePostsSkip.test_entry_id_없는_포스트_건너뛰기` (line 69)
- `TestRevisePostsSkip.test_본문_없는_포스트_건너뛰기` (line 86)
- `TestRevisePostsSkip.test_content_None_건너뛰기` (line 97)
- `TestRevisePostsFailure.test_수정_실패_시_FAILED_상태` (line 111)
- `TestRevisePostsFailure.test_로그인_실패_즉시_중단` (line 125)
- `TestRevisePostsBrowserLifecycle.test_예외_발생_시_브라우저_종료` (line 145)
- `TestRevisePostsBrowserLifecycle.test_빈_목록일_때_브라우저_미시작` (line 154)
- `TestRevisePostsDailyLimit.test_일일_제한_시_나머지_건너뛰기` (line 179)
- `TestRevisePostsDailyLimit.test_일일_제한_포스트_수정대기_복원` (line 199)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/application/test_revise_posts_usecase.py -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'enricher'`

- [ ] **Step 3: Refactor RevisePostsUseCase implementation**

Replace the entire file `src/application/use_cases/revise_posts.py` with:

```python
"""RevisePostsUseCase — Orchestrates the blog post revision workflow."""
import logging
from dataclasses import dataclass

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.domain.exceptions import DailyPublishLimitError
from src.domain.ports.browser_port import BrowserPort
from src.domain.ports.post_repository import PostRepository

logger = logging.getLogger(__name__)


@dataclass
class ReviseStats:
    revised: int = 0
    failed: int = 0
    skipped: int = 0


class RevisePostsUseCase:
    def __init__(
        self,
        repo: PostRepository,
        browser: BrowserPort,
        enricher: InternalLinkEnricher,
        max_posts: int = 5,
    ):
        self._repo = repo
        self._browser = browser
        self._enricher = enricher
        self._max_posts = max_posts

    def execute(self) -> ReviseStats:
        stats = ReviseStats()
        posts = self._repo.find_revision_pending(limit=self._max_posts)

        if not posts:
            logger.info("수정 대기 포스트 없음")
            return stats

        published_posts = self._repo.find_published(limit=50)
        hubs = self._enricher.identify_hubs(published_posts)

        self._browser.start()
        try:
            if not self._browser.login():
                logger.error("로그인 실패 — 수정 중단")
                return stats

            for post in posts:
                self._enricher.enrich_with_related_links(
                    post, published_posts, hubs,
                )
                self._enricher.attach_internal_link_map(post, published_posts)
                try:
                    self._revise_single(post, stats)
                except DailyPublishLimitError:
                    logger.warning(
                        "일일 발행 제한 도달 — 나머지 포스트 건너뜀 "
                        f"(수정: {stats.revised}, 실패: {stats.failed})"
                    )
                    break

        finally:
            self._browser.stop()

        return stats

    def _revise_single(self, post, stats: ReviseStats) -> None:
        if not post.is_revisable():
            logger.warning(f"수정 불가 포스트 건너뜀: row={post.row_index}")
            stats.skipped += 1
            return

        try:
            post.mark_revising()
            self._repo.save(post)

            result = self._browser.update(post)

            if result.success:
                post.mark_revised(result.url)
                stats.revised += 1
                logger.info(f"수정 완료: {post.keyword} → {result.url}")
            else:
                post.mark_failed(result.error)
                stats.failed += 1
                logger.error(f"수정 실패: {post.keyword} — {result.error}")

        except DailyPublishLimitError:
            post.reset_revising_to_revision_pending()
            self._repo.save(post)
            raise
        except Exception as e:
            post.mark_failed(str(e))
            stats.failed += 1
            logger.exception(f"수정 중 예외: {post.keyword}")
        finally:
            self._repo.save(post)
```

Key changes from the original:
- Removed `from dataclasses import replace` (no longer needed)
- Removed `from src.domain.entities.post import Post`
- Removed `from src.domain.services.internal_link_service import InternalLinkService`
- Added `from src.application.services.internal_link_enricher import InternalLinkEnricher`
- Constructor now accepts `enricher` as a parameter (replaces `self._link_service = InternalLinkService()`)
- `_enrich_with_related_links()` method deleted — calls `self._enricher.enrich_with_related_links()`
- `_attach_internal_link_map()` method deleted — calls `self._enricher.attach_internal_link_map()`
- `self._link_service.identify_hubs()` → `self._enricher.identify_hubs()`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/application/test_revise_posts_usecase.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/application/use_cases/revise_posts.py tests/unit/application/test_revise_posts_usecase.py
git commit -m "refactor(app): RevisePostsUseCase uses DI for enricher

Removes duplicated link enrichment methods, accepts InternalLinkEnricher
via constructor injection."
```

---

### Task 4: Update CLI Composition Root

**Files:**
- Modify: `src/interface/cli.py`

**Context:** The CLI creates Use Cases in two places:
1. `main()` function (line 533): Creates `PublishPostsUseCase`
2. `_revise()` function (line 182): Creates `RevisePostsUseCase`

Both need to assemble the new dependencies.

- [ ] **Step 1: Add imports to cli.py**

At the top of `src/interface/cli.py`, after the existing imports (around line 20), add:

```python
from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.domain.services.internal_link_service import InternalLinkService
from src.domain.services.publish_policy import PublishPolicy
from src.domain.services.quota_manager import QuotaManager
```

- [ ] **Step 2: Update main() — PublishPostsUseCase assembly**

In `main()`, replace lines 532-537 (the `PublishPostsUseCase` construction):

```python
    # Step 2: 발행
    stats = PublishPostsUseCase(
        repo=repo,
        browser=browser,
        max_posts=config.max_posts,
    ).execute()
```

with:

```python
    # Step 2: 발행
    link_service = InternalLinkService()
    enricher = InternalLinkEnricher(link_service)
    policy = PublishPolicy(max_posts=config.max_posts)
    quota = QuotaManager()
    stats = PublishPostsUseCase(
        repo=repo,
        browser=browser,
        enricher=enricher,
        policy=policy,
        quota=quota,
        max_posts=config.max_posts,
    ).execute()
```

- [ ] **Step 3: Update _revise() — RevisePostsUseCase assembly**

In `_revise()`, replace lines 181-186 (the `RevisePostsUseCase` construction):

```python
    # Step 2: 수정
    stats = RevisePostsUseCase(
        repo=repo,
        browser=browser,
        max_posts=config.max_posts,
    ).execute()
```

with:

```python
    # Step 2: 수정
    enricher = InternalLinkEnricher(InternalLinkService())
    stats = RevisePostsUseCase(
        repo=repo,
        browser=browser,
        enricher=enricher,
        max_posts=config.max_posts,
    ).execute()
```

- [ ] **Step 4: Run full test suite**

Run: `python3 -m pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 5: Run lint + typecheck + DDD validation**

Run: `ruff check src/ tests/ && python3 -m mypy src/ --ignore-missing-imports`
Expected: 0 issues

Run: `make validate-ddd` (or the equivalent DDD layer check script)
Expected: 0 violations. `InternalLinkEnricher` is in Application and imports only from Domain — this is allowed.

- [ ] **Step 6: Commit**

```bash
git add src/interface/cli.py
git commit -m "refactor(interface): update CLI composition root for new DI

Assembles InternalLinkEnricher, PublishPolicy, and QuotaManager at the
Composition Root and injects into PublishPostsUseCase and RevisePostsUseCase."
```

---

## Final Verification

After all tasks are complete:

- [ ] **Run full quality gate**

```bash
python3 -m pytest tests/unit/ -v --tb=short
ruff check src/ tests/
python3 -m mypy src/ --ignore-missing-imports
make validate-ddd
make coverage
```

Expected:
- All unit tests pass
- 0 lint warnings
- 0 type errors
- 0 DDD violations
- domain+app coverage ≥ 80%
