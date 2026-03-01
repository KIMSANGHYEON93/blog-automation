"""Credentials value object tests."""
from src.domain.value_objects.credentials import Credentials


class TestCredentials:
    def test_create_with_all_fields(self):
        c = Credentials(kakao_id="test@test.com", kakao_pw="pw", tistory_blog="myblog")
        assert c.kakao_id == "test@test.com"
        assert c.kakao_pw == "pw"
        assert c.tistory_blog == "myblog"

    def test_is_complete_true(self):
        c = Credentials(kakao_id="id", kakao_pw="pw", tistory_blog="blog")
        assert c.is_complete() is True

    def test_is_complete_false_missing_id(self):
        c = Credentials(kakao_id="", kakao_pw="pw", tistory_blog="blog")
        assert c.is_complete() is False

    def test_is_complete_false_missing_pw(self):
        c = Credentials(kakao_id="id", kakao_pw="", tistory_blog="blog")
        assert c.is_complete() is False

    def test_is_complete_false_missing_blog(self):
        c = Credentials(kakao_id="id", kakao_pw="pw", tistory_blog="")
        assert c.is_complete() is False
