"""Composition helpers for configured generation backends."""

from taxguide.config.models import GenerationConfig
from taxguide.generation.base import Generator
from taxguide.generation.openai_compatible import OpenAICompatibleGenerator


def create_generator(settings: GenerationConfig) -> Generator:
    """Create the configured generator without exposing backend details to callers."""
    if settings.provider == "openai_compatible":
        return OpenAICompatibleGenerator(
            settings.base_url,
            settings.model,
            timeout=settings.timeout,
            structured_output=settings.structured_output,
        )
    raise ValueError(f"Unsupported generation provider: {settings.provider}")
