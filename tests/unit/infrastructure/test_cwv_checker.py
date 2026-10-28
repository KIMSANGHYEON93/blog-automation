"""PageSpeedCwvAdapter — 모바일·데스크톱 측정과 실사용자 평가 파싱 (네트워크 없음)."""
from __future__ import annotations

import pytest
import requests

from src.infrastructure.seo import cwv_checker
from src.infrastructure.seo.cwv_checker import PageSpeedCwvAdapter


def _psi(lcp_ms: float, cls: float, score: float, field: str = "") -> dict:
    data: dict = {"lighthouseResult": {
        "audits": {
            "largest-contentful-paint": {"numericValue": lcp_ms},
            "cumulative-layout-shift": {"numericValue": cls},
        },
        "categories": {"performance": {"score": score}},
    }}
    if field:
        data["loadingExperience"] = {"overall_category": field}
    return data


class _Resp:
    def __init__(self, data: dict):
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._data


@pytest.fixture
def psi(monkeypatch):
    responses: dict = {}
    calls: list[str] = []

    def fake_get(url, params, timeout):
        calls.append(params["strategy"])
        r = responses[params["strategy"]]
        if isinstance(r, Exception):
            raise r
        return _Resp(r)

    monkeypatch.setattr(cwv_checker.requests, "get", fake_get)
    monkeypatch.delenv("PAGESPEED_API_KEY", raising=False)
    return responses, calls


def test_모바일과_데스크톱을_함께_측정한다(psi):
    responses, calls = psi
    responses["mobile"] = _psi(5300, 0.29, 0.51)
    responses["desktop"] = _psi(1800, 0.069, 0.74)

    r = PageSpeedCwvAdapter().check("https://x.tistory.com/1")

    assert calls == ["mobile", "desktop"]
    assert (r.lcp_seconds, r.cls_score, r.performance_score) == (5.3, 0.29, 51)
    assert r.desktop is not None
    d = r.desktop
    assert (d.lcp_seconds, d.cls_score, d.performance_score) == (1.8, 0.069, 74)
    assert r.desktop.passed is True


def test_LCP가_좋아도_CLS가_나쁘면_통과가_아니다(psi):
    responses, _ = psi
    responses["mobile"] = _psi(2000, 0.3, 0.8)
    responses["desktop"] = _psi(1000, 0.0, 0.95)

    assert PageSpeedCwvAdapter().check("https://x.tistory.com/1").passed is False


def test_실사용자_평가가_있으면_담는다(psi):
    responses, _ = psi
    responses["mobile"] = _psi(5000, 0.0, 0.6, field="SLOW")
    responses["desktop"] = _psi(1000, 0.0, 0.9)

    assert PageSpeedCwvAdapter().check("https://x.tistory.com/1").field_category == "SLOW"


def test_실사용자_데이터가_없으면_빈_값(psi):
    responses, _ = psi
    responses["mobile"] = _psi(5000, 0.0, 0.6)
    responses["desktop"] = _psi(1000, 0.0, 0.9)

    assert PageSpeedCwvAdapter().check("https://x.tistory.com/1").field_category == ""


def test_데스크톱_측정이_실패해도_모바일_결과는_남긴다(psi):
    responses, _ = psi
    responses["mobile"] = _psi(2000, 0.05, 0.9)
    responses["desktop"] = requests.ConnectionError("down")

    r = PageSpeedCwvAdapter().check("https://x.tistory.com/1")

    assert r.error == ""
    assert r.passed is True
    assert r.desktop is None


def test_모바일_측정이_실패하면_오류로_끝나고_데스크톱은_재지_않는다(psi):
    responses, calls = psi
    responses["mobile"] = requests.HTTPError("429 Client Error: Too Many Requests")

    r = PageSpeedCwvAdapter().check("https://x.tistory.com/1")

    assert "429" in r.error  # cli가 이 문자열로 한도 초과를 감지해 점검을 멈춘다
    assert calls == ["mobile"]
