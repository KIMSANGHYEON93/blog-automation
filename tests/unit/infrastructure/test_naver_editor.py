"""네이버 에디터 페이지 이동 — 로드가 끝나지 않는 리소스 하나에 발행 전체가 죽지 않게."""
from selenium.common.exceptions import TimeoutException

from src.infrastructure.browser.naver import editor


class _HangingSB:
    """open이 페이지 로드 제한에 걸리는 브라우저(2026-10-02·10-05 실측: MyBlog.naver)."""

    def __init__(self, error=None):
        self.error = error or TimeoutException("page load timeout")
        self.scripts: list[str] = []
        self.shots: list[str] = []
        self.driver = self

    @property
    def switch_to(self):
        raise RuntimeError("확인창 없음")

    def switch_to_default_content(self):
        pass

    def open(self, url):
        raise self.error

    def save_screenshot(self, path):
        self.shots.append(path)

    def execute_script(self, script):
        self.scripts.append(script)


def test_페이지_로드_제한에_걸리면_로딩을_멈추고_계속한다():
    sb = _HangingSB()
    editor._open(sb, "https://blog.naver.com/MyBlog.naver")
    assert "window.stop();" in sb.scripts


def test_SeleniumBase가_바꿔_던지는_로드_시간_초과도_멈추고_계속한다():
    # SeleniumBase는 시간 초과를 한 번 재시도한 뒤 일반 Exception으로 바꿔 던진다(2026-10-06)
    sb = _HangingSB(Exception("Retry of page load timed out after 30.0 seconds!"))
    editor._open(sb, "https://blog.naver.com/MyBlog.naver")
    assert "window.stop();" in sb.scripts
    assert sb.shots  # 멈춘 화면을 남겨 원인을 볼 수 있게


def test_시간_초과가_아닌_오류는_그대로_올린다():
    import pytest

    sb = _HangingSB(RuntimeError("chrome not reachable"))
    with pytest.raises(RuntimeError):
        editor._open(sb, "https://blog.naver.com/MyBlog.naver")
