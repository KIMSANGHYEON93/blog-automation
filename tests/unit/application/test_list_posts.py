"""ListPostsUseCase — 관리자 대시보드 게시물 목록 조회."""
from __future__ import annotations

from datetime import datetime

from src.application.use_cases.list_posts import ListPostsUseCase, PostQuery
from src.domain.entities.post import Post
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository


def _post(row, keyword, status=PostStatus.PENDING, body_len=3500, score=85, **kw):
    return Post(
        row_index=row, keyword=keyword, status=status,
        content=PostContent(title=f"{keyword} 제목", body_markdown="x" * body_len),
        quality_score=score, **kw,
    )


def _repo():
    return InMemoryPostRepository([
        _post(2, "OpenTelemetry 구축"),
        _post(3, "Istio vs Linkerd", body_len=100),
        _post(4, "Kafka 입문", PostStatus.PUBLISHED, published_url="https://b/4",
              published_at=datetime(2026, 9, 17, 21, 4)),
        _post(5, "Redis 오류", PostStatus.FAILED, error_message="Tistory 500"),
    ])


class TestListPosts:
    def test_전체_목록과_상태별_개수(self):
        page = ListPostsUseCase(_repo()).execute(PostQuery())
        assert [s.row_index for s in page.items] == [2, 3, 4, 5]
        assert page.counts[PostStatus.PENDING] == 2
        assert page.counts[PostStatus.PUBLISHED] == 1
        assert page.counts[PostStatus.FAILED] == 1
        assert page.total == 4

    def test_상태_필터(self):
        page = ListPostsUseCase(_repo()).execute(PostQuery(status=PostStatus.PENDING))
        assert [s.row_index for s in page.items] == [2, 3]
        assert page.total == 4  # 개수 요약은 필터와 무관하게 전체 기준

    def test_키워드_제목_검색은_대소문자_무시(self):
        page = ListPostsUseCase(_repo()).execute(PostQuery(search="istio"))
        assert [s.row_index for s in page.items] == [3]

    def test_발행_가능_여부와_사유(self):
        items = {s.row_index: s for s in ListPostsUseCase(_repo()).execute(PostQuery()).items}
        assert items[2].can_publish is True
        assert items[2].blockers == ()
        assert items[3].can_publish is False
        assert any("3000" in b for b in items[3].blockers)
        assert items[4].can_publish is False

    def test_요약_필드(self):
        items = {s.row_index: s for s in ListPostsUseCase(_repo()).execute(PostQuery()).items}
        assert items[4].published_url == "https://b/4"
        assert items[4].published_at == "2026-09-17 21:04"
        assert items[5].error_message == "Tistory 500"
        assert items[2].title == "OpenTelemetry 구축 제목"
        assert items[2].body_length == 3500

    def test_행_번호로_단건_조회(self):
        uc = ListPostsUseCase(_repo())
        assert uc.get(4).keyword == "Kafka 입문"
        assert uc.get(99) is None
