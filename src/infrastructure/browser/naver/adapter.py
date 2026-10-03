"""NaverBrowserAdapter — 네이버 블로그용 BrowserPort 구현.

로그인은 자동화하지 않는다. 네이버는 자동 입력 로그인에 캡차·기기 인증을 띄우므로,
`scripts/naver_blog.py login`으로 사람이 한 번 로그인(로그인 상태 유지 체크)한 프로필을
재사용한다. 세션이 죽었으면 login()이 False를 돌려 호출부가 LoginFailedError로 알린다.

draft_only=True(기본)면 임시저장까지만 하고 실패로 보고한다 — 시트 상태를 '발행완료'로
바꾸지 않기 위해서다. 공개 발행은 draft_only=False로 명시해야 한다.
"""
from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.domain.entities.post import Post
from src.domain.ports.browser_port import BrowserPort
from src.domain.services.photo_markers import PHOTO_LINE
from src.domain.value_objects.publish_result import PublishResult
from src.infrastructure.browser.naver import editor, login
from src.infrastructure.browser.naver.content import (
    build_naver_html,
    layout_blocks,
    normalize_tags,
    parse_log_no,
    split_sections,
)
from src.infrastructure.browser.naver.images import ImageFn, image_prompt
from src.infrastructure.browser.naver.inspect import check_published

# 대표 1장 + 소제목마다 1장, 상한
MAX_IMAGES = 5

logger = logging.getLogger(__name__)

# 티스토리 .browser_data 와 분리 — 두 파이프라인이 같은 프로필 락을 두고 다투지 않게
DEFAULT_PROFILE_DIR = ".browser_data_naver"
DEFAULT_PHOTO_DIR = "uploads/naver"
DRAFT_ONLY_MESSAGE = "임시저장만 완료(draft_only) — 네이버 글쓰기 > 임시저장에서 확인"


class NaverBrowserAdapter(BrowserPort):
    def __init__(self, blog_id: str, profile_dir: str = DEFAULT_PROFILE_DIR,
                 headless: bool = False, draft_only: bool = True,
                 min_delay: int = 300, max_delay: int = 900,
                 screenshot_dir: str = "logs/naver", image_fn: ImageFn | None = None,
                 thumbnail_fn: Callable[[str, bytes, str], bytes] | None = None,
                 photo_dir: str = DEFAULT_PHOTO_DIR):
        # headless 기본 False: 네이버는 헤드리스 탐지가 강하다(참고 저장소 공통 권고)
        self._blog_id = blog_id
        self._profile_dir = os.path.abspath(profile_dir)
        self._headless = headless
        self._draft_only = draft_only
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._screenshot_dir = Path(screenshot_dir)
        self._image_fn = image_fn
        self._thumbnail_fn = thumbnail_fn  # 첫 사진(대표)에 제목을 얹는다
        self._photo_dir = Path(photo_dir)  # 대시보드에서 직접 올린 사진
        self.images_uploaded = 0  # 마지막 글에서 업로드가 확인된 사진 수(임시저장 시험 보고용)
        self._sb = None
        self._sb_context = None

    def start(self) -> None:
        from seleniumbase import SB

        os.makedirs(self._profile_dir, exist_ok=True)
        context = SB(
            headless=self._headless,
            chromium_arg=f"--user-data-dir={self._profile_dir}",
        )
        self._sb = context.__enter__()
        self._sb_context = context
        logger.info("네이버 브라우저 시작")

    def stop(self) -> None:
        if self._sb_context:
            try:
                self._sb_context.__exit__(None, None, None)
            except Exception as e:
                logger.warning(f"네이버 브라우저 종료 중 오류 (무시): {e}")
            finally:
                self._sb = None
                self._sb_context = None

    def login(self) -> bool:
        ok = editor.is_logged_in(self._sb, self._blog_id)
        if not ok:
            logger.error("네이버 세션 만료 — scripts/naver_blog.py login 으로 다시 로그인 필요")
        return ok

    def relogin(self, login_id: str, login_pw: str) -> tuple[bool, str]:
        """대시보드 '네이버 다시 로그인' — 브라우저를 열어 자동 입력하고 폰 승인을 기다린다."""
        if not login_id or not login_pw:
            return False, "NAVER_LOGIN_ID·NAVER_LOGIN_PW가 .env에 없음"
        self.start()
        try:
            outcome = login.auto_login(self._sb, login_id, login_pw)
            if outcome is not login.LoginOutcome.SUCCESS:
                # 로그인 화면에는 아이디가 보이므로 실패 스크린샷을 남기지 않는다
                return False, login.LOGIN_MESSAGES[outcome]
            if not editor.is_logged_in(self._sb, self._blog_id):
                return False, "로그인은 됐지만 블로그 세션 확인 실패 — 직접 확인"
            return True, login.LOGIN_MESSAGES[login.LoginOutcome.SUCCESS]
        finally:
            self.stop()

    def publish(self, post: Post) -> PublishResult:
        content = post.content
        if content is None or not content.has_body():
            return PublishResult.fail("본문 없음")
        try:
            result = self._write(post)
        except editor.NaverEditorError as e:
            logger.error(f"네이버 발행 실패 [{post.keyword}]: {e}")
            self._save_failure_screenshot(post)
            return PublishResult.fail(str(e))
        self._pause()
        return result

    def update(self, post: Post) -> PublishResult:
        """발행된 글을 같은 주소에서 고쳐 쓴다: 수정 화면 → 제목 교체 → 본문 비우기 → 다시 붙이기.

        네이버는 마지막 '발행'을 눌러야 수정이 저장된다. 그 전에 멈추면 기존 글은 그대로다.
        """
        content = post.content
        if content is None or not content.has_body():
            return PublishResult.fail("본문 없음")
        log_no = post.entry_id or parse_log_no(post.published_url or "")
        if not log_no:
            return PublishResult.fail("글 번호가 없어 수정할 글을 찾을 수 없음")
        markdown = content.body_markdown or ""
        title = content.title_or_fallback(post.keyword)
        try:
            editor.open_update_editor(self._sb, self._blog_id, log_no)
            editor.replace_title(self._sb, title)
            editor.clear_body(self._sb)
            self._paste_sections(post.keyword, markdown, title)
            if self._draft_only:
                return PublishResult.fail("수정 시험만 함 — 저장하지 않아 기존 글은 그대로")
            filled = editor.body_text_length(self._sb)
            # ponytail: 마크다운 기호·줄바꿈이 빠지므로 절반을 하한으로 둔다.
            # 붙여넣기가 중간에 끊긴 경우만 잡는다 — 더 엄밀히는 소제목 수 대조
            if filled < len(markdown) // 2:
                return PublishResult.fail(
                    f"붙인 본문이 {filled}자로 모자라 발행을 누르지 않음 — 기존 글은 그대로",
                )
            return self._confirm(post, markdown)
        except editor.NaverEditorError as e:
            logger.error(f"네이버 수정 실패 [{post.keyword}]: {e}")
            self._save_failure_screenshot(post)
            return PublishResult.fail(str(e))

    def _write(self, post: Post) -> PublishResult:
        assert post.content is not None
        content = post.content
        markdown = content.body_markdown or ""
        editor.open_editor(self._sb, self._blog_id)
        editor.fill_title(self._sb, content.title_or_fallback(post.keyword))
        self._paste_sections(post.keyword, markdown, content.title_or_fallback(post.keyword))
        if self._draft_only:
            editor.save_draft(self._sb)
            return PublishResult.fail(DRAFT_ONLY_MESSAGE)
        return self._confirm(post, markdown)

    def _confirm(self, post: Post, markdown: str) -> PublishResult:
        """발행 레이어에서 카테고리·태그를 넣고 확정한 뒤 공개 글을 점검한다."""
        assert post.content is not None
        tags = normalize_tags(post.content.tag_list())
        url = editor.publish(self._sb, tags, post.category)
        return PublishResult.ok(
            url=url, entry_id=parse_log_no(url),
            warnings=tuple(self._inspect(url, post.category, len(tags), markdown)),
        )

    def _inspect(self, url: str, category: str, tag_count: int, markdown: str) -> list[str]:
        """발행된 글을 열어 점검한다. 점검이 실패해도 발행 결과는 바꾸지 않는다."""
        try:
            stats = editor.collect_post_stats(self._sb, url)
        except Exception as e:
            logger.warning(f"발행 후 점검 실패(발행은 완료): {e}")
            return [f"발행 후 점검을 하지 못함: {e}"]
        headings = sum(1 for heading, _ in split_sections(markdown) if heading)
        warnings = check_published(
            stats, category=category, tag_count=tag_count, heading_count=headings,
            max_images=(MAX_IMAGES if self._image_fn else 0)
            + len(PHOTO_LINE.findall(markdown)),  # 직접 올린 사진은 상한과 따로
        )
        for warning in warnings:
            logger.warning(f"발행 후 점검: {warning} — {url}")
        return warnings

    def _paste_sections(self, keyword: str, markdown: str, title: str) -> None:
        """대표 사진 → 도입부 → (소제목 → 사진 → 본문)… 순서로 커서 뒤에 이어 붙인다."""
        editor.focus_body(self._sb)
        self.images_uploaded = 0
        first_image = True
        for kind, value in layout_blocks(markdown, MAX_IMAGES):
            if kind == "text":
                editor.paste_html(self._sb, build_naver_html(value), value)
                continue
            if kind == "photo":
                if self._insert_photo(value):
                    self.images_uploaded += 1
                continue
            # 첫 사진은 네이버가 대표(썸네일)로 쓴다 — 거기에만 제목을 얹는다
            if self._insert_image(keyword, value, title if first_image else ""):
                self.images_uploaded += 1
            first_image = False

    def _insert_photo(self, filename: str) -> bool:
        """직접 올린 사진을 붙인다. 파일이 없으면 그 자리만 비우고 계속한다."""
        path = self._photo_dir / filename
        if not path.is_file():
            logger.warning(f"올린 사진 파일이 없음 — 사진 없이 계속: {path}")
            return False
        return editor.paste_image(self._sb, path.read_bytes())

    def _insert_image(self, keyword: str, heading: str, thumbnail_title: str = "") -> bool:
        """사진 자리 하나를 채운다. 생성에 실패하면 그 자리는 비운다.

        자리 수(상한)는 layout_blocks가 정한다 — 확인이 늦은 사진 때문에 자리를 더 만들지 않는다
        (2026-09-26 실측: 늦게 올라간 사진 때문에 6장이 됨).
        """
        if self._image_fn is None:
            return False
        cover = bool(thumbnail_title) and self._thumbnail_fn is not None
        data = self._image_fn(image_prompt(keyword, heading, cover=cover))
        if data is not None and cover and self._thumbnail_fn is not None:
            data = self._thumbnail_fn(thumbnail_title, data, keyword)
        return data is not None and editor.paste_image(self._sb, data)

    def _save_failure_screenshot(self, post: Post) -> None:
        if self._sb is None:
            return
        try:
            self._screenshot_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = self._screenshot_dir / f"{stamp}_row{post.row_index}.png"
            self._sb.save_screenshot(str(path))
            logger.info(f"실패 스크린샷: {path}")
        except Exception as e:
            # 진단용이라 실패해도 발행 결과를 바꾸지 않는다
            logger.warning(f"실패 스크린샷 저장 못함: {e}")

    def _pause(self) -> None:
        delay = random.randint(self._min_delay, self._max_delay)
        logger.info(f"다음 네이버 발행까지 {delay}초 대기")
        time.sleep(delay)
