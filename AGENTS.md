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

## Milestone documentation discipline

- Complete every milestone with its documentation updated in the same change set.
- Keep `README.md` and `docs/architecture.md` aligned with the functionality that actually exists; remove stale phase or scope claims.
- Update the relevant module documentation, configuration examples and CLI examples whenever behavior, contracts or operational steps change.
- Record cross-cutting architectural decisions in an ADR under `docs/adr/`.
- Document assumptions, operational prerequisites, intentionally deferred work and known limitations without presenting future milestones as implemented.
- Before declaring a milestone complete, review the changed files against the documentation and explicitly report which documentation was updated. If no documentation changed, explain why it was unnecessary.

## Before completing a task

Run:

uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src

Report:
- files changed
- tests executed
- documentation updated
- assumptions
- known limitations
