# TaxGuide Norway — Development Instructions

## Project principles

- Work only on the requested issue.
- Do not implement functionality from future milestones.
- Inspect the repository before making changes.
- Preserve the modular architecture.
- Prefer explicit interfaces and dependency injection.
- Use Python 3.12+.
- Use Pydantic v2 for domain/configuration models.
- Use pytest, Ruff and mypy.
- Add tests for all new behavior.
- Avoid unnecessary dependencies.
- Do not introduce LangChain, LlamaIndex or Haystack.
- Do not add embeddings, vector databases, retrieval or LLM functionality before their corresponding milestone.

## Before completing a task

Run:

uv run pytest
uv run ruff check .
uv run mypy src

Report:
- files changed
- tests executed
- assumptions
- known limitations