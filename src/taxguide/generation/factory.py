"""Composition helpers for configured generation backends."""

from taxguide.config.models import GenerationConfig
from taxguide.generation.base import Generator
from taxguide.generation.openai_compatible import OpenAICompatibleGenerator
from taxguide.generation.vertex import VertexAIGenerator


def create_generator(settings: GenerationConfig) -> Generator:
    """Create the configured generator without exposing backend details to callers."""
    if settings.provider == "openai_compatible":
        return OpenAICompatibleGenerator(
            settings.base_url,
            settings.model,
            timeout=settings.timeout,
            structured_output=settings.structured_output,
        )
    if settings.provider == "vertex_ai":
        return VertexAIGenerator(
            settings.model,
            project=settings.vertex_project,
            location=settings.vertex_location,
            timeout=settings.timeout,
            structured_output=settings.structured_output,
            thinking_budget=settings.vertex_thinking_budget,
        )
    raise ValueError(f"Unsupported generation provider: {settings.provider}")
