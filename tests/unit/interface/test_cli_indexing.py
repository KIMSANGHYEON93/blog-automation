"""--submit-index 조립 — 일반 블로그 글은 기본 설정에서 Indexing API로 제출하지 않는다.

Indexing API는 JobPosting·BroadcastEvent(VideoObject) 페이지 전용이다
(https://developers.google.com/search/apis/indexing-api/v3/quickstart).
"""
from __future__ import annotations

from src.domain.ports.seo_port import IndexingSubmitResult
from src.infrastructure.config import Config
from src.interface import cli


def _config(monkeypatch, **env) -> Config:
    monkeypatch.delenv("INDEXING_API_ENABLED", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Config.from_env()


def test_INDEXING_API_ENABLED_기본값은_꺼짐(monkeypatch):
    assert _config(monkeypatch).indexing_api_enabled is False
    assert _config(monkeypatch, INDEXING_API_ENABLED="true").indexing_api_enabled is True


def test_기본_설정이면_시트도_API도_건드리지_않고_이유만_남긴다(monkeypatch, caplog):
    def _boom(*args, **kwargs):
        raise AssertionError("기본 설정에서 시트·Indexing API를 호출하면 안 된다")

    monkeypatch.setattr(cli, "GoogleSheetsPostRepository", _boom)
    monkeypatch.setattr(cli, "_build_notification", _boom)
    from src.infrastructure.seo import indexing_submitter
    monkeypatch.setattr(indexing_submitter.GscIndexingSubmitAdapter, "submit", _boom)
    config = _config(monkeypatch)
    monkeypatch.setattr(config, "validate", _boom)

    with caplog.at_level("INFO"):
        cli._submit_index(config)

    assert "INDEXING_API_ENABLED" in caplog.text
    assert "사이트맵" in caplog.text
    assert "Search Console" in caplog.text


class _Repo:
    def __init__(self, *args, **kwargs):
        pass

    def find_published(self, limit: int = 50):
        from src.domain.entities.post import Post
        from src.domain.value_objects.post_status import PostStatus

        post = Post(row_index=2, keyword="k", status=PostStatus.PUBLISHED,
                    published_url="https://b.tistory.com/1")
        return [post]

    def save(self, post) -> None:
        raise AssertionError("요청 접수를 시트에 기록하면 안 된다")


class _Notifier:
    def __init__(self):
        self.sent: list[str] = []

    def send(self, msg: str) -> None:
        self.sent.append(msg)


def test_플래그를_켜도_알림은_요청_접수이지_색인_완료가_아니다(monkeypatch):
    notifier = _Notifier()
    monkeypatch.setattr(cli, "GoogleSheetsPostRepository", _Repo)
    monkeypatch.setattr(cli, "_build_notification", lambda: notifier)
    from src.infrastructure.seo import indexing_submitter
    monkeypatch.setattr(indexing_submitter.GscIndexingSubmitAdapter, "submit",
                        lambda self, url: IndexingSubmitResult(url=url, success=True))
    config = _config(monkeypatch, INDEXING_API_ENABLED="true")
    monkeypatch.setattr(config, "validate", lambda: None)

    cli._submit_index(config)

    assert len(notifier.sent) == 1
    assert "요청 접수=1" in notifier.sent[0]
    assert "색인 완료 아님" in notifier.sent[0]
