"""수정 이력(최초 발행일 보존)과 검증 당시 본문 지문 — Post 엔티티 규칙."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from src.domain.entities.post import Post, body_fingerprint
from src.domain.value_objects.post_content import PostContent
from src.domain.value_objects.post_status import PostStatus

BODY = "## 본문\n" + "가" * 3000


def _pending(body: str = BODY, **kwargs) -> Post:
    return Post(row_index=2, keyword="OAuth 개념", status=PostStatus.PENDING,
                content=PostContent(title="제목", body_markdown=body), quality_score=85, **kwargs)


class TestRevisionHistory:
    def test_수정해도_최초_발행일은_그대로_수정일과_횟수는_따로(self):
        first = datetime(2026, 9, 1, 9, 0)
        post = Post(row_index=2, keyword="k", status=PostStatus.REVISING,
                    published_at=first, entry_id="1", revision_count=2)

        post.mark_revised("https://t/1")

        assert post.published_at == first
        assert post.revised_at is not None and post.revised_at > first
        assert post.revision_count == 3


class TestBodyFingerprint:
    def test_사진_표시_CRLF_끝공백은_지문에_영향_없음(self):
        base = body_fingerprint(BODY)
        assert body_fingerprint(BODY.replace("\n", "\r\n")) == base
        assert body_fingerprint(BODY + "\n\n[[사진:a1.jpg]]\n") == base
        assert body_fingerprint(BODY + "\n\n<!-- 사진: a desk -->  \n") == base
        capture = "\n\n[[사진:c1.jpg]]\n\n출처: https://docs.x.io/a (캡처 2026-10-08)\n"
        assert body_fingerprint(BODY + capture) == base

    def test_글자가_바뀌면_지문이_다르다(self):
        assert body_fingerprint(BODY + "덧붙임") != body_fingerprint(BODY)


class TestVerificationStale:
    def test_지문이_없는_예전_행은_기존_점수를_믿는다(self):
        assert _pending().publish_blockers() == []

    def test_검증_뒤_본문이_바뀌면_재검증_필요로_막힌다(self):
        post = _pending(verified_body_hash=body_fingerprint(BODY))
        post.content = replace(post.content, body_markdown=BODY + "\n사람이 쓴 경험")

        assert any("재검증" in b for b in post.publish_blockers())
        assert post.quality_score == 85  # 점수는 그대로 — 올리지도 지우지도 않는다

    def test_관리자_승인은_현재_본문에만_유효(self):
        post = _pending(verified_body_hash=body_fingerprint(BODY))
        post.content = replace(post.content, body_markdown=BODY + "\n경험")
        post.approve_current_body()
        assert post.publish_blockers() == []

        post.content = replace(post.content, body_markdown=BODY + "\n또 바꿈")
        assert any("재검증" in b for b in post.publish_blockers())

    def test_다시_생성하면_지문과_승인을_지운다(self):
        post = _pending(verified_body_hash="x", approved_body_hash="y")
        post.reset_for_regeneration()
        assert post.verified_body_hash == "" and post.approved_body_hash == ""

    def test_수정_발행도_검증_무효면_막힌다(self):
        post = _pending(verified_body_hash=body_fingerprint(BODY), entry_id="1")
        post.status = PostStatus.REVISION_PENDING
        post.content = replace(post.content, body_markdown=BODY + "\n바꿈")
        assert post.is_revisable() is False
