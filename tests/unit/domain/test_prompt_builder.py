"""Tests for PromptBuilder domain service."""
from src.domain.services.prompt_builder import PromptBuilder


class TestPromptBuilder:
    def test_build_with_category_hint(self):
        prompt = PromptBuilder.build("Docker 컨테이너", category="가이드")
        assert prompt.is_valid()
        assert "step-by-step" in prompt.prompt
        assert "Docker 컨테이너" in prompt.prompt

    def test_build_with_title_override(self):
        prompt = PromptBuilder.build(
            "Docker", category="비교", title="Docker vs Podman 비교",
        )
        assert "Docker vs Podman 비교" in prompt.prompt
        assert "Docker" not in prompt.prompt.split(",")[0] or "Docker vs" in prompt.prompt

    def test_build_unknown_category_uses_default(self):
        prompt = PromptBuilder.build("테스트", category="알수없는카테고리")
        assert "modern tech illustration" in prompt.prompt

    def test_build_empty_category(self):
        prompt = PromptBuilder.build("테스트", category="")
        assert "modern tech illustration" in prompt.prompt

    def test_build_all_known_categories(self):
        known = ["용어", "비교", "트러블슈팅", "AI", "Windows", "Linux", "가이드", "트렌드"]
        for cat in known:
            prompt = PromptBuilder.build("test", category=cat)
            assert prompt.is_valid()
            # Default style should NOT appear for known categories
            assert "modern tech illustration" not in prompt.prompt

    def test_base_suffix_always_present(self):
        prompt = PromptBuilder.build("anything")
        assert "professional blog thumbnail" in prompt.prompt
