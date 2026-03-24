"""Tests for ImagePrompt value object."""
from src.domain.value_objects.image_prompt import ImagePrompt


class TestImagePrompt:
    def test_valid_prompt(self):
        p = ImagePrompt(prompt="A beautiful landscape")
        assert p.is_valid()

    def test_empty_prompt_is_invalid(self):
        p = ImagePrompt(prompt="")
        assert not p.is_valid()

    def test_whitespace_only_is_invalid(self):
        p = ImagePrompt(prompt="   ")
        assert not p.is_valid()

    def test_default_values(self):
        p = ImagePrompt(prompt="test")
        assert p.style == "digital-art"
        assert p.size == "1024x1024"
        assert p.quality == "standard"

    def test_frozen(self):
        import pytest

        p = ImagePrompt(prompt="test")
        with pytest.raises(AttributeError):
            p.prompt = "changed"  # type: ignore[misc]
