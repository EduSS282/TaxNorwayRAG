# TaxGuide Norway

TaxGuide Norway is a modular Python system for acquiring, normalizing, indexing, and retrieving
official Norwegian tax documentation. The repository currently implements the offline corpus
pipeline, four retrieval modes, tax-year-aware filtering, deterministic tax routing, and the
contracts used by grounded generation.

It now provides an end-to-end `taxguide answer` command that composes deterministic routing,
tax-year resolution, retrieval, bounded context, local generation, validation, and safe abstention.
An HTTP API and frontend are not implemented.

## Implemented today

- bounded crawling of public `skatteetaten.no` HTML, with manifests and duplicate detection;
- HTML parsing, normalization, and deterministic document/version identities;
- fixed-token, recursive, and structural chunking;
- Ollama and local `sentence-transformers` embedding adapters;
- Qdrant indexing and dense retrieval;
- in-memory BM25 sparse retrieval, reciprocal-rank fusion, and Qwen reranking;
- strict pre-ranking tax-year filters and cross-year result validation;
- deterministic topic, intent, risk, and route classification;
- automatic creation and schema validation of the Qdrant collection during indexed corpus builds;
- bounded generation context, OpenAI-compatible local generation, Pydantic JSON parsing, citation,
  quote-span and tax-year validation, explicit application statuses, and safe abstention;
- unit/integration evaluation utilities and an opt-in live retrieval benchmark harness.

See [current architecture](docs/architecture.md) for component boundaries and
[grounded-generation status](docs/generation.md) for the remaining end-to-end work.

## Installation

Requirements:

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/);
- Docker for the provided local Qdrant service;
- Ollama when using the default embedding configuration;
- a separately managed reranker service for `--mode reranked`.

From the repository root:

```bash
uv sync --locked
uv run taxguide --help
```

The Python test suite does not require a GPU or live model server. Runtime model weights are not
downloaded by TaxGuide itself.

## Local workflow

Start Qdrant and Ollama, then pull the default embedding model:

```bash
docker compose up -d qdrant
ollama pull qwen3-embedding:0.6b
```

The first indexed corpus build creates the configured cosine collection using the embedder's
reported dimension. Existing collections are validated before any upsert. Follow
[local runtime](docs/local-runtime.md) for model processes, hardware allocation, and security notes.

Acquire and inspect official pages:

```bash
uv run taxguide crawl "https://www.skatteetaten.no/en/person/taxes/tax-return/" --max-pages 25 --max-depth 2
uv run taxguide corpus build --url-prefix "/en/person/taxes/" --language en --dry-run
uv run taxguide corpus build --url-prefix "/en/person/taxes/" --language en --index
```

Compare retrieval modes against the same indexed collection:

```bash
uv run taxguide retrieve "What is the minimum standard deduction for 2025?" --mode dense --limit 5
uv run taxguide retrieve "What is the minimum standard deduction for 2025?" --mode sparse --limit 5
uv run taxguide retrieve "What is the minimum standard deduction for 2025?" --mode hybrid --limit 5
uv run taxguide retrieve "What is the minimum standard deduction for 2025?" --mode reranked --candidate-limit 10 --limit 5
```

With the generator running at the configured OpenAI-compatible endpoint:

```bash
uv run taxguide answer "What is the minimum standard deduction for 2025?" --mode hybrid
uv run taxguide answer "Where do I report foreign income?" --tax-year 2025 --mode reranked --json
```

`answer` returns one of `answered`, `clarification_required`, `abstained`, or `failed`. It does not
emit an unvalidated model answer.

The CLI also supports direct local-file ingestion and chunk inspection:

```bash
uv run taxguide parse tests/fixtures/html/skatteetaten_basic.html --url "https://www.skatteetaten.no/en/example"
uv run taxguide inspect tests/fixtures/html/skatteetaten_nested_headings.html --url "https://www.skatteetaten.no/en/example"
uv run taxguide parse tests/fixtures/html/skatteetaten_basic.html --url "https://www.skatteetaten.no/en/example" --json > normalized-example.json
uv run taxguide chunk normalized-example.json --strategy structural
```

The CLI loads `configs/base.yaml` when it exists in the working directory. `--config` selects an
explicit base file and `--overlay` recursively merges and validates an environment-specific
overlay. Paths are relative to the working directory.

## Architecture summary

```text
Offline
URL → crawler → raw HTML + manifest → parser → normalizer → chunker
                                                       → embedder → Qdrant

Online retrieval
question → tax-year resolution → metadata filter → dense/sparse/hybrid → optional reranker

Grounded generation
retrieved chunks → context builder → grounded prompt → generator → parse/validate → abstain/answer
```

Primary source directories:

```text
src/taxguide/crawling/     Bounded acquisition and crawl artifacts
src/taxguide/ingestion/    Parsing, normalization, and ingestion orchestration
src/taxguide/chunking/     Deterministic chunking strategies
src/taxguide/embeddings/   Embedding contracts and adapters
src/taxguide/vectorstores/ Qdrant adapter
src/taxguide/retrieval/    Dense, sparse, hybrid, and temporal retrieval
src/taxguide/reranking/    Local, HTTP, and llama.cpp rerankers
src/taxguide/query/        Intent, risk, and tax-year resolution
src/taxguide/rules/        Deterministic routing decisions
src/taxguide/context/      Bounded generation context
src/taxguide/generation/   Generation contracts, prompts, citations, and validation
src/taxguide/evaluation/   Retrieval and generation metrics
```

## Verification

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

The live retrieval benchmark and grounded-generation smoke test are opt-in and require a populated
Qdrant collection plus the configured model services. See [retrieval](docs/retrieval.md) and
[grounded generation](docs/generation.md). No reproducible real-corpus baseline is committed yet.

## Current limitations and next milestone

- Service startup and model downloads remain external operational steps.
- `CachingBatchingEmbedder` provides process-local batching/cache behavior but is not composed by
  the configured embedding factory and is not persistent.
- Quote spans are checked for bounds and non-blank source text, but the schema does not carry a
  copied quote for semantic equality checks.
- Prompt instructions mark retrieved text as untrusted, but prompt isolation is not a complete
  security boundary; deterministic validation remains mandatory.
- Context selection budgets chunk tokens and does not yet count rendered metadata, JSON schema, or
  chat-template overhead.
- Claim-level faithfulness is evaluated only through offline injected evaluators, not enforced by
  the online validator.
- The checked-in generation fixture is intentionally small, and the live retrieval benchmark has
  no committed production-quality corpus, results, thresholds, or hardware manifest.
- The crawler does not execute JavaScript, submit forms, enter authenticated areas, or traverse
  interactive wizard branches.
- TaxGuide provides information from official evidence; it is not a substitute for professional
  tax advice or an eligibility determination.

The next coherent milestones are the persistent role-aware embedding cache and reproducible real
retrieval/generation benchmarks. See [grounded generation](docs/generation.md) for the implemented
contract and its remaining limitations.

## Documentation

- [Architecture](docs/architecture.md)
- [Local runtime and hardware](docs/local-runtime.md)
- [Desktop, laptop, and Oracle deployment](docs/three-machine-deployment.md)
- [Grounded generation status](docs/generation.md)
- [Crawler](docs/crawler.md)
- [Corpus workflow](docs/corpus.md)
- [Retrieval and evaluation](docs/retrieval.md)
- [Tax routing](docs/routing.md)
- [Reranker service](docs/reranker-service.md)
- [Architecture reference](Design/norway_tax_rag_architecture.md)
