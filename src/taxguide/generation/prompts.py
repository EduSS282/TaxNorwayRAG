"""Prompt construction for evidence-bound tax-answer generation."""

import json

from taxguide.context.builder import GenerationContext
from taxguide.generation.base import ChatMessage
from taxguide.generation.models import RagAnswer

_SYSTEM_INSTRUCTIONS = """You are TaxGuide Norway, a careful assistant for Norwegian tax
information.
Use only the retrieved evidence supplied by the user. Do not use outside knowledge or
invent tax rules. Cite every factual tax claim using only the supplied evidence IDs.
Distinguish source facts from cautious inferences. Do not assume tax residency,
eligibility, or a tax year. If the evidence is insufficient, answer with a safe
abstention, explain what is missing, set confidence to low, and provide no citations.
Recommend the official source when appropriate. Return only JSON matching the schema."""


def build_grounded_messages(
    question: str, context: GenerationContext, *, tax_year: int | None = None
) -> list[ChatMessage]:
    """Create deterministic messages that bind the model to retrieved evidence."""
    if not question.strip():
        raise ValueError("generation question must not be blank")
    requested_year = str(tax_year) if tax_year is not None else "not specified"
    schema = json.dumps(RagAnswer.model_json_schema(), sort_keys=True, separators=(",", ":"))
    user_content = (
        f"Question:\n{question}\n\n"
        f"Requested tax year: {requested_year}\n\n"
        f"Retrieved evidence:\n{context.render()}\n\n"
        f"Return a JSON value matching this schema:\n{schema}"
    )
    return [
        {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
        {"role": "user", "content": user_content},
    ]
