"""네이버 에디터 페이지 이동 — 로드가 끝나지 않는 리소스 하나에 발행 전체가 죽지 않게."""
from selenium.common.exceptions import TimeoutException

from src.infrastructure.browser.naver import editor


class _HangingSB:
    """open이 페이지 로드 제한에 걸리는 브라우저(2026-10-02·10-05 실측: MyBlog.naver)."""

    def __init__(self):
        self.scripts: list[str] = []
        self.driver = self

    @property
    def switch_to(self):
        raise RuntimeError("확인창 없음")

    def switch_to_default_content(self):
        pass

    def open(self, url):
        raise TimeoutException("page load timeout")

    def execute_script(self, script):
        self.scripts.append(script)


def test_페이지_로드_제한에_걸리면_로딩을_멈추고_계속한다():
    sb = _HangingSB()
    editor._open(sb, "https://blog.naver.com/MyBlog.naver")
    assert "window.stop();" in sb.scripts
