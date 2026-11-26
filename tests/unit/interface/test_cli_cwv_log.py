"""cli의 CWV 점검 로그 — 어댑터가 넘긴 오류 문자열에 키가 섞여 있어도 로그에 남기지 않는다.

어댑터가 이미 가리지만, 다른 CwvPort 구현이나 예전 경로로 키가 섞여 들어와도
cli 로그(logs/publish_*.log)에는 남지 않아야 한다.
"""
from __future__ import annotations

from src.domain.entities.post import Post
from src.domain.ports.notification_port import NotificationPort
from src.domain.ports.seo_port import CwvPort, CwvResult
from src.domain.value_objects.post_status import PostStatus
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository
from src.interface import cli

FAKE_KEY = "AIzaSyFAKE_cli-0123456789abcdefghijklmnop"


class _LeakyCwv(CwvPort):
    """키가 든 요청 URL을 오류로 돌려주는 가짜 어댑터 (가짜 HTTPError 문자열)."""

    def __init__(self, status: str = "429"):
        self.calls = 0
        self._status = status

    def check(self, url: str) -> CwvResult:
        self.calls += 1
        return CwvResult(error=(
            f"{self._status} Client Error: Too Many Requests for url: "
            "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
            f"?url=x&strategy=mobile&key={FAKE_KEY}"
        ))


class _Silent(NotificationPort):
    def send(self, message: str, level: str = "INFO") -> bool:
        return True


def _published(row: int) -> Post:
    post = Post(row_index=row, keyword=f"글{row}")
    post.status = PostStatus.PUBLISHED
    post.published_url = f"https://example.tistory.com/{row}"
    return post


def test_CWV_실패_로그에_API_키가_남지_않는다(caplog):
    repo = InMemoryPostRepository([_published(2), _published(3)])
    cwv = _LeakyCwv(status="500")

    with caplog.at_level("WARNING"):
        cli._run_cwv_checks(repo, _Silent(), cwv, sleep=lambda _s: None)

    assert "CWV 실패: 글2" in caplog.text
    assert FAKE_KEY not in caplog.text
    assert cwv.calls == 2


def test_429면_가린_뒤에도_한도_초과로_보고_멈춘다(caplog):
    repo = InMemoryPostRepository([_published(2), _published(3)])
    cwv = _LeakyCwv(status="429")

    with caplog.at_level("WARNING"):
        cli._run_cwv_checks(repo, _Silent(), cwv, sleep=lambda _s: None)

    assert "PageSpeed API rate limit" in caplog.text
    assert cwv.calls == 1
    assert FAKE_KEY not in caplog.text
