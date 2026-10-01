"""통합 대시보드: 플랫폼별 앱을 /naver·/tistory에 붙인 WSGI 하나.

세션 공유는 각 앱이 같은 시크릿과 쿠키 경로 '/'를 쓰는 것으로 된다(create_app).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Callable

from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.utils import redirect

from src.interface.web.app import HUB_TABS


def build_hub(apps: Mapping[str, Flask]) -> DispatcherMiddleware:
    expected = {key for key, _, _ in HUB_TABS}
    if set(apps) != expected:
        raise ValueError(f"통합 대시보드에는 {sorted(expected)} 앱이 모두 필요합니다")
    home = HUB_TABS[0][2]

    def to_home(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        return redirect(home)(environ, start_response)

    return DispatcherMiddleware(to_home, {href.rstrip("/"): apps[key] for key, _, href in HUB_TABS})
