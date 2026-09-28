"""네이버 블로그 수동 도구 — 1회 로그인과 임시저장 시험.

사용법:
    python scripts/naver_blog.py login    # 창에서 직접 로그인 ('로그인 상태 유지' 체크)
    python scripts/naver_blog.py check    # 저장된 세션이 살아 있는지
    python scripts/naver_blog.py draft post.md --title "제목"   # 임시저장까지만

.env: NAVER_BLOG_ID=<블로그 아이디>  (비밀번호는 넣지 않는다 — 로그인은 사람이 한다)
세션은 .browser_data_naver/ 에 남는다(.gitignore).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# `python scripts/naver_blog.py`로 실행하면 sys.path에 scripts/만 들어가 src를 못 찾는다
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.domain.entities.post import Post  # noqa: E402
from src.domain.value_objects.post_content import PostContent  # noqa: E402
from src.infrastructure.browser.naver.adapter import (  # noqa: E402
    DEFAULT_PROFILE_DIR,
    DRAFT_ONLY_MESSAGE,
    NaverBrowserAdapter,
)
from src.infrastructure.browser.naver.editor import NaverEditorError  # noqa: E402
from src.infrastructure.browser.naver.images import (  # noqa: E402
    pollinations_image_fn,
    title_thumbnail,
)

load_dotenv()

LOGIN_URL = "https://nid.naver.com/nidlogin.login"


def _blog_id() -> str:
    blog_id = os.getenv("NAVER_BLOG_ID", "").strip()
    if not blog_id:
        sys.exit(".env에 NAVER_BLOG_ID를 넣어 주세요.")
    return blog_id


def _login(adapter: NaverBrowserAdapter) -> int:
    adapter._sb.open(LOGIN_URL)
    print("브라우저에서 네이버에 로그인하세요. '로그인 상태 유지'를 꼭 체크하세요.")
    input("로그인을 마쳤으면 Enter ▶ ")
    ok = adapter.login()
    print("세션 저장 완료" if ok else "로그인이 확인되지 않았습니다. 다시 시도하세요.")
    return 0 if ok else 1


def _check(adapter: NaverBrowserAdapter) -> int:
    ok = adapter.login()
    print("세션 유효" if ok else "세션 만료 — login 을 다시 실행하세요.")
    return 0 if ok else 1


def _draft(adapter: NaverBrowserAdapter, path: Path, title: str) -> int:
    if not adapter.login():
        print("세션 만료 — login 을 먼저 실행하세요.")
        return 1
    body = path.read_text(encoding="utf-8")
    post = Post(row_index=0, keyword=title, content=PostContent(title=title, body_markdown=body))
    result = adapter.publish(post)
    print(result.error or result.url)
    return 0 if result.error == DRAFT_ONLY_MESSAGE else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="네이버 블로그 로그인·임시저장 시험")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login")
    sub.add_parser("check")
    draft = sub.add_parser("draft")
    draft.add_argument("markdown", type=Path)
    draft.add_argument("--title", required=True)
    args = parser.parse_args()

    # 시험 도구라 발행 간 대기는 두지 않고, 공개 발행은 하지 않는다(draft_only=True).
    adapter = NaverBrowserAdapter(
        _blog_id(), profile_dir=DEFAULT_PROFILE_DIR, draft_only=True, min_delay=0, max_delay=0,
        image_fn=pollinations_image_fn(os.getenv("POLLINATIONS_API_KEY", "")),
        thumbnail_fn=title_thumbnail,
    )
    adapter.start()
    try:
        if args.cmd == "login":
            return _login(adapter)
        if args.cmd == "check":
            return _check(adapter)
        return _draft(adapter, args.markdown, args.title)
    except NaverEditorError as e:
        print(f"실패: {e}")
        return 1
    finally:
        adapter.stop()


if __name__ == "__main__":
    sys.exit(main())
