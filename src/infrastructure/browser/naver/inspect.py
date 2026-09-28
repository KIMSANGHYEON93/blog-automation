"""발행 후 점검 — 공개 글에서 읽은 수치를 기대값과 비교해 경고 목록을 만든다.

사람이 공개 글을 열어 찾던 문제들이다: 카테고리 미지정(2026-09-23), 태그 1개만(09-23),
번호만 남은 줄(09-24), 사진 6장(09-26).
"""
from __future__ import annotations


def check_published(
    stats: dict, *, category: str, tag_count: int, heading_count: int, max_images: int,
) -> list[str]:
    warnings = []
    if category and stats.get("category") != category:
        warnings.append(f"카테고리가 '{stats.get('category')}'(기대 '{category}')")
    if stats.get("tags", 0) < tag_count:
        warnings.append(f"태그 {stats.get('tags', 0)}개(기대 {tag_count}개)")
    images = stats.get("images", 0)
    if images > max_images:
        warnings.append(f"사진 {images}장(상한 {max_images}장)")
    elif images == 0:
        warnings.append("사진이 없음")
    if stats.get("quotes", 0) != heading_count:
        warnings.append(f"소제목 인용구 {stats.get('quotes', 0)}개(기대 {heading_count}개)")
    if stats.get("orphan_numbers", 0):
        warnings.append(f"번호만 남은 줄 {stats['orphan_numbers']}개")
    return warnings
