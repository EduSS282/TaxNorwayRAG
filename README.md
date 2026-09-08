# TaxGuide Norway

A modular Python foundation for processing Norwegian tax documentation saved as HTML.
This iteration implements **Phase 0 + Phase 1** only: configuration,
domain models, and verifiable local ingestion.

**Current phase does not implement RAG retrieval or LLM generation.**
It does not include crawling, chunking, embeddings, databases, a frontend, or agents.

## Installation

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From the repository root:

```bash
uv sync --locked
uv run taxguide --help
```

The initial installation downloads dependencies; execution and tests run locally,
without APIs, a GPU, or Docker. `uv.lock` pins the resolved versions.

## Usage

```bash
uv run taxguide parse tests/fixtures/html/skatteetaten_basic.html --url "https://www.skatteetaten.no/en/example"
uv run taxguide inspect tests/fixtures/html/skatteetaten_nested_headings.html --url "https://www.skatteetaten.no/en/example"
uv run taxguide parse tests/fixtures/html/skatteetaten_basic.html --url "https://www.skatteetaten.no/en/example" --json > data/normalized/example.json
uv run taxguide inspect tests/fixtures/html/skatteetaten_noise.html --url "https://www.skatteetaten.no/en/example" --config configs/base.yaml --overlay configs/local.yaml
```

`parse` displays metadata; `inspect` also displays the normalized text. Both accept
`--json` to serialize the complete document. Logs are written to stderr.
Files are not persisted automatically: output redirection is explicit.

The CLI loads `configs/base.yaml` when it exists in the current directory; outside
the repository, it uses the same typed defaults. `--config` requires the file to
exist. `--overlay` recursively merges values and validates the result.
Configuration paths are relative to the working directory.
No secrets or environment variables are required.

## Architecture

```text
LocalHtmlSource → RawDocument → SkatteetatenHtmlParser → ParsedDocument
                                                        ↓
                                                    Normalizer → Document
```

The `DocumentSource`, `DocumentParser`, and `DocumentNormalizer` interfaces support
component injection into `IngestionPipeline`. The domain depends only on Pydantic and
the standard library. The CLI constructs components and presents domain errors.
Documents retain the original URL, absolute local path, domain, source path,
timezone-aware timestamp, and SHA-256 hash of the original bytes.

```text
configs/                Base configuration and overlays
src/taxguide/config/    Models and YAML loading
src/taxguide/domain/    Documents, sections, paragraphs, links, and errors
src/taxguide/sources/   Loading contract and local HTML adapter
src/taxguide/ingestion/ Hashing, parsing, normalization, and orchestration
src/taxguide/cli/       Typer commands
tests/                  Unit tests, integration tests, and synthetic fixtures
data/                   Local data directories (ignored by Git)
docs/                   Architecture, ingestion, and architecture decision records
```

## Verification

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pre-commit install
```

GitHub Actions runs installation from the lockfile, tests, linting, formatting checks,
and type checking. Pre-commit hooks check Ruff rules, formatting, YAML, and whitespace.

## Assumptions and limitations

- Fixtures are synthetic; they are neither tax guidance nor downloaded official pages.
- Input must be UTF-8, with an optional BOM, and use Skatteetaten HTTP(S) URLs.
- `retrieved_at` records local loading time by default; it does not invent a download date.
  For captures with a known timestamp, a clock can be injected into `LocalHtmlSource`.
- Heading levels and order allow the hierarchy to be reconstructed without chunking.
- The parser uses preferred selectors and semantic fallbacks; compatibility with every
  real Skatteetaten page variant is not guaranteed.
- Simple tables are represented as rows and cells; rowspan/colspan are not expanded.
- JavaScript is not executed, and external resources are not loaded.

See [architecture](docs/architecture.md) and [ingestion](docs/ingestion.md) for details.

## Current follow-on work

Phase 2 adds fixed-token, recursive, and structural chunking over the normalized
`Document` representation. Retrieval, embeddings, vector databases, and LLM
generation remain out of scope.
