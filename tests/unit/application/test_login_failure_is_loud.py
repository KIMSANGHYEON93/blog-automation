"""로그인 실패는 예외로 올라가야 한다 — 조용한 종료는 장애를 숨긴다.

2026-05-06 ~ 09-21 약 4개월 반 동안 파이프라인이 죽어 있었는데 아무도 몰랐다.
원인 구조:
    if not browser.login():
        logger.error(...); return      # 예외 없음
    → main() 정상 종료 → run_pipeline_b.sh EXIT_CODE=0 → launchd는 성공으로 기록

main()은 이미 Exception을 잡아 알림을 보내고 re-raise하므로, 로그인 실패가
예외로 올라오기만 하면 알림과 non-zero 종료가 함께 해결된다.
"""
from __future__ import annotations

import pytest

from src.application.use_cases.publish_posts import PublishPostsUseCase
from src.application.use_cases.revise_posts import RevisePostsUseCase
from src.domain.exceptions import LoginFailedError
from src.infrastructure.browser.mock_browser import MockBrowserAdapter
from src.infrastructure.persistence.in_memory_repo import InMemoryPostRepository
from tests.unit.application.test_publish_posts_usecase import (
    make_publishable_post,
    make_use_case,
)
from tests.unit.application.test_revise_posts_usecase import (
    make_revisable_post,
)
from tests.unit.application.test_revise_posts_usecase import (
    make_use_case as make_revise_use_case,
)


class TestLoginFailedError:
    def test_도메인_예외_계층에_속한다(self):
        from src.domain.exceptions import DomainError

        assert issubclass(LoginFailedError, DomainError)

    def test_메시지에_원인이_담긴다(self):
        err = LoginFailedError("카카오 2FA 미승인")
        assert "카카오 2FA 미승인" in str(err)


class TestPublishRaisesOnLoginFailure:
    def test_로그인_실패는_예외(self):
        repo = InMemoryPostRepository([make_publishable_post(1)])
        browser = MockBrowserAdapter(login_success=False)
        use_case = make_use_case(repo, browser)

        with pytest.raises(LoginFailedError):
            use_case.execute()

    def test_예외가_나도_브라우저는_닫힌다(self):
        repo = InMemoryPostRepository([make_publishable_post(1)])
        browser = MockBrowserAdapter(login_success=False)
        use_case = make_use_case(repo, browser)

        with pytest.raises(LoginFailedError):
            use_case.execute()
        assert browser.stopped is True, "브라우저가 남으면 다음 실행이 락에 걸린다"

    def test_발행은_한_건도_시도되지_않는다(self):
        repo = InMemoryPostRepository(
            [make_publishable_post(1), make_publishable_post(2)]
        )
        browser = MockBrowserAdapter(login_success=False)
        use_case = make_use_case(repo, browser)

        with pytest.raises(LoginFailedError):
            use_case.execute()
        assert browser.published_posts == []


class TestReviseRaisesOnLoginFailure:
    def test_로그인_실패는_예외(self):
        repo = InMemoryPostRepository([make_revisable_post(1, entry_id="100")])
        browser = MockBrowserAdapter(login_success=False)
        use_case = make_revise_use_case(repo, browser)

        with pytest.raises(LoginFailedError):
            use_case.execute()

    def test_예외가_나도_브라우저는_닫힌다(self):
        repo = InMemoryPostRepository([make_revisable_post(1, entry_id="100")])
        browser = MockBrowserAdapter(login_success=False)
        use_case = make_revise_use_case(repo, browser)

        with pytest.raises(LoginFailedError):
            use_case.execute()
        assert browser.stopped is True


class TestUseCaseTypes:
    """회귀 방지 — 시그니처가 바뀌어도 예외 계약은 유지."""

    @pytest.mark.parametrize("cls", [PublishPostsUseCase, RevisePostsUseCase])
    def test_유스케이스가_존재한다(self, cls):
        assert hasattr(cls, "execute")
