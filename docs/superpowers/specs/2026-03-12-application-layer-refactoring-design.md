# Application Layer Refactoring Design

## Context

blog-automation 프로젝트의 Application 계층(DDD 4-Layer)에서 유지보수성 개선이 필요.

### 문제점

1. **코드 중복**: `PublishPostsUseCase`(93-118줄)와 `RevisePostsUseCase`(63-102줄)에 `_enrich_with_related_links()`와 `_attach_internal_link_map()` 메서드가 완전히 동일하게 존재 (~40줄 x 2)
2. **DI 원칙 위반**: Use Case 생성자에서 Domain Service(`InternalLinkService`, `PublishPolicy`, `QuotaManager`)를 직접 인스턴스화 → 테스트 격리 불가
3. **Fat Use Case**: `PublishPostsUseCase`가 169줄로, 오케스트레이션 + 내부 링크 + 에러처리 + 쿼터 관리를 모두 담당

### 선택한 접근법

**Approach A: Application Service 추출** — 중복 로직을 Application 계층 내 공유 서비스로 추출하고, Domain Service는 생성자 주입으로 전환.

## Design

### 1. InternalLinkEnricher (신규 Application Service)

**파일**: `src/application/services/internal_link_enricher.py`

```python
class InternalLinkEnricher:
    """발행/수정 시 공통으로 사용하는 내부 링크 강화 서비스."""

    def __init__(self, link_service: InternalLinkService):
        self._link_service = link_service

    def enrich_with_related_links(
        self, post: Post, published: list[Post], hubs: list[Post],
    ) -> None:
        """관련 글 HTML을 본문 끝에 추가."""
        # PublishPostsUseCase._enrich_with_related_links()와 동일 로직

    def attach_internal_link_map(
        self, post: Post, published: list[Post],
    ) -> None:
        """keyword→URL 매핑을 post.internal_link_map에 첨부."""
        # PublishPostsUseCase._attach_internal_link_map()와 동일 로직
```

### 2. PublishPostsUseCase 수정

```python
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
        self._enricher = enricher  # 주입
        self._policy = policy      # 주입 (기존: 직접 생성)
        self._quota = quota         # 주입 (기존: 직접 생성)
        self._max_posts = max_posts
```

- `_enrich_with_related_links()` 삭제 → `self._enricher.enrich_with_related_links()` 호출
- `_attach_internal_link_map()` 삭제 → `self._enricher.attach_internal_link_map()` 호출
- `_publish_single()` 유지 (발행 전용 로직)

### 3. RevisePostsUseCase 수정

```python
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
        self._enricher = enricher  # 주입 (기존: InternalLinkService 직접 생성)
        self._max_posts = max_posts
```

- `_enrich_with_related_links()` 삭제
- `_attach_internal_link_map()` 삭제
- `_link_service` 직접 사용 부분 → `self._enricher.enrich_with_related_links()` 호출
- `identify_hubs()` 호출도 enricher가 내부 link_service를 통해 처리

### 4. CLI (Composition Root) 수정

```python
# src/interface/cli.py — main() 내 DI 조립

from src.application.services.internal_link_enricher import InternalLinkEnricher
from src.domain.services.internal_link_service import InternalLinkService
from src.domain.services.publish_policy import PublishPolicy
from src.domain.services.quota_manager import QuotaManager

link_service = InternalLinkService()
enricher = InternalLinkEnricher(link_service)
policy = PublishPolicy(max_posts=config.max_posts)
quota = QuotaManager()

stats = PublishPostsUseCase(
    repo=repo, browser=browser,
    enricher=enricher, policy=policy, quota=quota,
    max_posts=config.max_posts,
).execute()
```

`_revise()` 함수도 동일하게 enricher 주입.

### 5. identify_hubs() 처리

현재 두 Use Case 모두 `execute()` 내에서 `self._link_service.identify_hubs(published_posts)`를 호출. 이를 InternalLinkEnricher에 위임:

```python
class InternalLinkEnricher:
    def identify_hubs(self, published: list[Post]) -> list[Post]:
        return self._link_service.identify_hubs(published)
```

## 변경 파일 목록

| 파일 | 변경 | 레이어 |
|------|------|--------|
| `src/application/services/__init__.py` | 신규 (빈 파일) | Application |
| `src/application/services/internal_link_enricher.py` | 신규 (~50줄) | Application |
| `src/application/use_cases/publish_posts.py` | 수정 (169→~110줄) | Application |
| `src/application/use_cases/revise_posts.py` | 수정 (135→~75줄) | Application |
| `src/interface/cli.py` | 수정 (DI 조립 추가) | Interface |
| `tests/unit/application/test_internal_link_enricher.py` | 신규 (~80줄) | Test |
| `tests/unit/application/test_publish_posts_usecase.py` | 수정 (DI 반영) | Test |
| `tests/unit/application/test_revise_posts_usecase.py` | 수정 (DI 반영) | Test |

## DDD 계층 규칙 준수

- `InternalLinkEnricher`는 Application 계층 → Domain만 의존 (InternalLinkService, Post)
- 의존 방향: Interface → Application → Domain ← Infrastructure (변경 없음)
- `make validate-ddd` 통과 보장

## 검증 기준

1. `make test-unit` — 전체 테스트 통과
2. `make lint && make typecheck` — 0 warnings, 0 errors
3. `make validate-ddd` — 0 violations
4. `make coverage` — domain+app ≥ 80%
