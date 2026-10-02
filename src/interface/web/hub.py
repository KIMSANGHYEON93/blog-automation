"""통합 대시보드: 플랫폼별 앱을 /naver·/tistory에 붙인 WSGI 하나.

세션 공유는 각 앱이 같은 시크릿과 쿠키 경로 '/'를 쓰는 것으로 된다(create_app).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Callable

from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.utils import redirect
from werkzeug.wrappers import Response

from src.interface.web.app import HUB_TABS


def build_hub(apps: Mapping[str, Flask]) -> DispatcherMiddleware:
    expected = {key for key, _, _ in HUB_TABS}
    if set(apps) != expected:
        raise ValueError(f"통합 대시보드에는 {sorted(expected)} 앱이 모두 필요합니다")
    home = HUB_TABS[0][2]

    def to_home(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        # 브라우저의 /favicon.ico를 /naver/로 보내면 쿠키 없는 요청이 네이버 로그인까지 가서
        # 티스토리 화면을 볼 때도 로그에 네이버 로그인이 찍힌다 — 아이콘은 비워 둔다
        if environ.get("PATH_INFO") == "/favicon.ico":
            return Response(status=204)(environ, start_response)
        return redirect(home)(environ, start_response)

    return DispatcherMiddleware(to_home, {href.rstrip("/"): apps[key] for key, _, href in HUB_TABS})
