"""SeleniumCategorySyncAdapter._parse_categories() unit tests.

Tistory category.json 응답의 하위 카테고리(children) 파싱 검증.
"""
from __future__ import annotations

from src.domain.ports.category_sync_port import RemoteCategory
from src.infrastructure.browser.category_sync_adapter import SeleniumCategorySyncAdapter


class TestParseCategoriesFlat:
    """기존 flat 구조 파싱 (하위 호환)."""

    def test_single_top_level(self):
        data = {
            "categories": [
                {"id": "100", "label": "카테고리A", "parent": "", "entryCount": 5},
            ],
        }
        result = SeleniumCategorySyncAdapter._parse_categories(data)
        assert len(result) == 1
        assert result[0] == RemoteCategory(
            name="카테고리A", category_id="100", parent="", entry_count=5,
        )

    def test_empty_categories(self):
        assert SeleniumCategorySyncAdapter._parse_categories({"categories": []}) == []
        assert SeleniumCategorySyncAdapter._parse_categories({}) == []


class TestParseCategoriesNested:
    """Tistory 실제 구조: children 배열에 하위 카테고리 포함."""

    TISTORY_SAMPLE = {
        "categories": [
            {
                "id": "966408",
                "label": "본것",
                "parent": "",
                "entryCount": 10,
                "children": [],
            },
            {
                "id": "966384",
                "label": "배운것",
                "parent": "",
                "entryCount": 50,
                "children": [
                    {
                        "id": "991463",
                        "label": "용어",
                        "parent": "966384",
                        "entryCount": 20,
                        "children": [],
                    },
                    {
                        "id": "992000",
                        "label": "비교",
                        "parent": "966384",
                        "entryCount": 15,
                        "children": [],
                    },
                ],
            },
            {
                "id": "1174373",
                "label": "해본것",
                "parent": "",
                "entryCount": 5,
                "children": [
                    {
                        "id": "1174400",
                        "label": "가이드",
                        "parent": "1174373",
                        "entryCount": 3,
                        "children": [],
                    },
                ],
            },
        ],
    }

    def test_children_are_included(self):
        result = SeleniumCategorySyncAdapter._parse_categories(self.TISTORY_SAMPLE)
        names = {r.name for r in result}
        # 부모 3 + 자식 3 = 6
        assert len(result) == 6
        assert names == {"본것", "배운것", "용어", "비교", "해본것", "가이드"}

    def test_child_has_correct_parent(self):
        result = SeleniumCategorySyncAdapter._parse_categories(self.TISTORY_SAMPLE)
        by_name = {r.name: r for r in result}

        assert by_name["용어"].parent == "966384"
        assert by_name["비교"].parent == "966384"
        assert by_name["가이드"].parent == "1174373"

    def test_child_has_correct_id(self):
        result = SeleniumCategorySyncAdapter._parse_categories(self.TISTORY_SAMPLE)
        by_name = {r.name: r for r in result}

        assert by_name["용어"].category_id == "991463"
        assert by_name["비교"].category_id == "992000"

    def test_parent_comes_before_children(self):
        """부모가 자식보다 먼저 나와야 함 (순서 보장)."""
        result = SeleniumCategorySyncAdapter._parse_categories(self.TISTORY_SAMPLE)
        names = [r.name for r in result]

        assert names.index("배운것") < names.index("용어")
        assert names.index("배운것") < names.index("비교")
        assert names.index("해본것") < names.index("가이드")

    def test_deeply_nested_children(self):
        """3단계 깊이 중첩도 파싱."""
        data = {
            "categories": [
                {
                    "id": "1", "label": "L1", "parent": "", "entryCount": 0,
                    "children": [
                        {
                            "id": "2", "label": "L2", "parent": "1", "entryCount": 0,
                            "children": [
                                {
                                    "id": "3", "label": "L3", "parent": "2",
                                    "entryCount": 0, "children": [],
                                },
                            ],
                        },
                    ],
                },
            ],
        }
        result = SeleniumCategorySyncAdapter._parse_categories(data)
        assert len(result) == 3
        names = [r.name for r in result]
        assert names == ["L1", "L2", "L3"]

    def test_entry_count_preserved(self):
        result = SeleniumCategorySyncAdapter._parse_categories(self.TISTORY_SAMPLE)
        by_name = {r.name: r for r in result}

        assert by_name["배운것"].entry_count == 50
        assert by_name["용어"].entry_count == 20
