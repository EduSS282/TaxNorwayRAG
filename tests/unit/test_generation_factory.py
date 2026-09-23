"""Tests for configured generator composition."""

from taxguide.config.models import GenerationConfig
from taxguide.generation.factory import create_generator
from taxguide.generation.openai_compatible import OpenAICompatibleGenerator


def test_generation_factory_builds_the_configured_openai_compatible_adapter() -> None:
    settings = GenerationConfig(
        base_url="http://generator.example",
        model="test-model",
        timeout=42.0,
        structured_output=True,
    )

    generator = create_generator(settings)

    assert isinstance(generator, OpenAICompatibleGenerator)
    assert generator.model_id == "test-model"
