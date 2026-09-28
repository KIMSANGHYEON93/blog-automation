"""발행 후 점검 — 공개 글에서 읽은 수치와 기대값 비교."""
from src.infrastructure.browser.naver.inspect import check_published

GOOD = {"category": "TechNova", "tags": 10, "images": 5, "quotes": 5, "orphan_numbers": 0}


def _check(stats, **expected):
    base = {"category": "TechNova", "tag_count": 10, "heading_count": 5, "max_images": 5}
    base.update(expected)
    return check_published(stats, **base)


def test_기대대로면_경고_없음():
    assert _check(GOOD) == []


def test_카테고리가_다르면_경고():
    warnings = _check({**GOOD, "category": "낙서장"})
    assert warnings == ["카테고리가 '낙서장'(기대 'TechNova')"]


def test_카테고리를_정하지_않았으면_검사하지_않는다():
    assert _check({**GOOD, "category": "낙서장"}, category="") == []


def test_태그가_모자라면_경고():
    # 2026-09-23: 10개 중 1개만 붙은 적이 있다
    assert _check({**GOOD, "tags": 1}) == ["태그 1개(기대 10개)"]


def test_사진이_상한을_넘거나_하나도_없으면_경고():
    assert _check({**GOOD, "images": 6}) == ["사진 6장(상한 5장)"]  # 2026-09-26 실제로 6장
    assert _check({**GOOD, "images": 0}) == ["사진이 없음"]


def test_인용구_소제목_수가_다르면_경고():
    assert _check({**GOOD, "quotes": 3}) == ["소제목 인용구 3개(기대 5개)"]


def test_번호만_남은_줄이_있으면_경고():
    # 2026-09-24: '1.'만 윗줄에 남는 문제가 있었다
    assert _check({**GOOD, "orphan_numbers": 2}) == ["번호만 남은 줄 2개"]
