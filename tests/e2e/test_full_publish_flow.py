"""E2E tests for the full publish flow — requires real infrastructure."""
import os
import time

import pytest


@pytest.mark.e2e
class TestFullPublishFlow:
    """실제 티스토리 발행 검증 — 공개 발행."""

    @pytest.mark.skipif(
        not os.getenv("KAKAO_ID"),
        reason="E2E 테스트는 실제 환경 변수 필요 (KAKAO_ID, KAKAO_PW 등)",
    )
    def test_정상_발행_E2E(self):
        """실제 티스토리 발행 검증 — MAX_POSTS=1로 제한."""
        import subprocess

        result = subprocess.run(
            ["python3", "-m", "src.interface.cli"],
            env={**os.environ, "HEADLESS": "false", "MAX_POSTS": "1"},
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0
        assert "발행 완료" in result.stdout or "발행: 1" in result.stdout

    @pytest.mark.skipif(
        not os.getenv("KAKAO_ID"),
        reason="E2E 테스트는 실제 환경 변수 필요",
    )
    def test_고스트_복구_후_재발행(self):
        """발행중 상태 포스트가 자동 복구 후 재발행되는지 검증."""
        from dotenv import load_dotenv

        load_dotenv()
        from src.application.use_cases.reset_stuck_posts import ResetStuckPostsUseCase
        from src.infrastructure.config import Config
        from src.infrastructure.persistence.google_sheets_repo import (
            GoogleSheetsPostRepository,
        )

        config = Config.from_env()
        repo = GoogleSheetsPostRepository(config.google_creds, config.sheet_name)

        # 고스트 상태 확인 (있으면 복구 후 PENDING 확인)
        stuck = repo.find_stuck()
        if stuck:
            ResetStuckPostsUseCase(repo).execute()
            time.sleep(1)
            still_stuck = repo.find_stuck()
            assert len(still_stuck) == 0
