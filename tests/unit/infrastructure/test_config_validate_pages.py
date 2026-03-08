"""Config.validate_pages() 단위 테스트."""
import os
from unittest.mock import patch

import pytest

from src.infrastructure.config import Config


def _make_config(**overrides) -> Config:
    """테스트용 Config 생성. 기본값: 모든 필수 필드 채움."""
    defaults = dict(
        kakao_id="test@kakao.com",
        kakao_pw="pw123",
        tistory_blog="test-blog",
        google_creds="credentials.json",
        sheet_name="test_sheet",
        max_posts=5,
        headless=True,
        min_delay=1,
        max_delay=2,
        contact_email="test@example.com",
        owner_name="테스터",
        sitemap_output="sitemap.xml",
        site_profile_path="site_profile.json",
    )
    defaults.update(overrides)
    return Config(**defaults)


class TestValidatePages:
    def test_필수_변수_모두_있으면_통과(self):
        config = _make_config()
        config.validate_pages()  # 예외 없음

    def test_contact_email_누락_시_오류(self):
        config = _make_config(contact_email="")
        with pytest.raises(OSError, match="CONTACT_EMAIL"):
            config.validate_pages()

    def test_owner_name_누락_시_오류(self):
        config = _make_config(owner_name="")
        with pytest.raises(OSError, match="OWNER_NAME"):
            config.validate_pages()

    def test_kakao_id_누락_시_오류(self):
        config = _make_config(kakao_id="")
        with pytest.raises(OSError, match="KAKAO_ID"):
            config.validate_pages()

    def test_tistory_blog_누락_시_오류(self):
        config = _make_config(tistory_blog="")
        with pytest.raises(OSError, match="TISTORY_BLOG"):
            config.validate_pages()

    def test_복수_필드_누락_시_모두_표시(self):
        config = _make_config(contact_email="", owner_name="")
        with pytest.raises(OSError, match="CONTACT_EMAIL") as exc_info:
            config.validate_pages()
        assert "OWNER_NAME" in str(exc_info.value)


class TestFromEnvNewFields:
    def test_환경변수_로드(self):
        env = {
            "KAKAO_ID": "id",
            "KAKAO_PW": "pw",
            "TISTORY_BLOG": "blog",
            "CONTACT_EMAIL": "me@test.com",
            "OWNER_NAME": "홍길동",
        }
        with patch.dict(os.environ, env, clear=False):
            config = Config.from_env()
        assert config.contact_email == "me@test.com"
        assert config.owner_name == "홍길동"

    def test_환경변수_미설정_시_빈문자열(self):
        env = {
            "CONTACT_EMAIL": "",
            "OWNER_NAME": "",
        }
        with patch.dict(os.environ, env, clear=False):
            config = Config.from_env()
        assert config.contact_email == ""
        assert config.owner_name == ""
