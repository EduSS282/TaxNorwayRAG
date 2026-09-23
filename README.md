# TaxGuide Norway

TaxGuide Norway is a modular Python system for acquiring, normalizing, indexing, and retrieving
official Norwegian tax documentation. The repository currently implements the offline corpus
pipeline, four retrieval modes, tax-year-aware filtering, deterministic tax routing, and the
contracts used by grounded generation.

It does **not yet provide an end-to-end answer command or API**. The generation adapter, prompt,
context builder, citation schema, validation, abstention policy, and evaluation primitives exist,
but they are not composed into a service that turns a question into a validated answer.

## Implemented today

- bounded crawling of public `skatteetaten.no` HTML, with manifests and duplicate detection;
- HTML parsing, normalization, and deterministic document/version identities;
- fixed-token, recursive, and structural chunking;
- Ollama and local `sentence-transformers` embedding adapters;
- Qdrant indexing and dense retrieval;
- in-memory BM25 sparse retrieval, reciprocal-rank fusion, and Qwen reranking;
- strict pre-ranking tax-year filters and cross-year result validation;
- deterministic topic, intent, risk, and route classification;
- bounded generation context, structured answer/citation models, prompt construction, citation
  validation, and safe abstention primitives;
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

Start Qdrant and Ollama, ensure that the configured Qdrant collection exists, and pull the default
embedding model:

```bash
docker compose up -d qdrant
ollama pull qwen3-embedding:0.6b
```

Collection creation is currently an explicit operational prerequisite; TaxGuide does not create or
validate it automatically. Follow [local runtime](docs/local-runtime.md) for the PowerShell setup,
model processes, hardware allocation, and security notes.

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

Implemented generation primitives, not yet orchestrated
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

The live retrieval benchmark is opt-in and requires a populated Qdrant collection plus embedding
and reranker services. See [retrieval](docs/retrieval.md). No reproducible real-corpus baseline is
committed yet.

## Current limitations and next milestone

- Qdrant collection creation, schema checks, service startup, and model downloads are external
  operational steps.
- `CachingBatchingEmbedder` provides process-local batching/cache behavior but is not composed by
  the configured embedding factory and is not persistent.
- `taxguide answer` and a grounded RAG service do not exist yet.
- Generated JSON is not yet parsed and validated in one orchestrated path; quote spans are not
  checked against source text, and retrieved text has no dedicated prompt-injection sanitization.
- The checked-in generation fixture is intentionally small, and the live retrieval benchmark has
  no committed production-quality corpus, results, thresholds, or hardware manifest.
- The crawler does not execute JavaScript, submit forms, enter authenticated areas, or traverse
  interactive wizard branches.
- TaxGuide provides information from official evidence; it is not a substitute for professional
  tax advice or an eligibility determination.

The next coherent milestone is the [grounded generation orchestration](docs/generation.md):
collection lifecycle checks, generator configuration/factory, a `GroundedRagService`, an `answer`
entry point, fail-closed validation, end-to-end tests, and documentation in the same change set.

## Documentation

- [Architecture](docs/architecture.md)
- [Local runtime and hardware](docs/local-runtime.md)
- [Grounded generation status](docs/generation.md)
- [Crawler](docs/crawler.md)
- [Corpus workflow](docs/corpus.md)
- [Retrieval and evaluation](docs/retrieval.md)
- [Tax routing](docs/routing.md)
- [Reranker service](docs/reranker-service.md)
- [Architecture reference](Design/norway_tax_rag_architecture.md)
