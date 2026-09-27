# TaxGuide Norway

TaxGuide Norway is a modular Python system for acquiring, normalizing, indexing, and retrieving
official Norwegian tax documentation. The repository currently implements the offline corpus
pipeline, four retrieval modes, tax-year-aware filtering, deterministic tax routing, and the
contracts used by grounded generation.

It provides an end-to-end `taxguide answer` command and a FastAPI HTTP boundary over the same
retrieval, reranking, and grounded-answer services. A Next.js frontend in `frontend/` provides a
local question interface, cited sources, tax-year/language controls, and a developer inspector.

## Implemented today

- bounded crawling of public `skatteetaten.no` HTML, with named source policies, capture
  manifests, and duplicate detection;
- domain/path-constrained crawling with robots and bounded `Retry-After` handling, plus source
  change detection across recrawls;
- HTML parsing, normalization, and deterministic document/version identities;
- fixed-token, recursive, and structural chunking;
- Ollama and local `sentence-transformers` embedding adapters;
- Qdrant indexing and dense retrieval;
- in-memory BM25 sparse retrieval, reciprocal-rank fusion, and Qwen reranking;
- strict pre-ranking tax-year filters and cross-year result validation;
- explicit annual-rate crawling (`--year`), checked against the fetched official year selector;
- deterministic topic, intent, risk, and route classification;
- multilingual deterministic routing with explicit uncertain-scope clarification and independent
  eligibility/amount risk checks; see [routing](docs/routing.md);
- automatic creation and schema validation of the Qdrant collection during indexed corpus builds;
- incremental indexing that verifies chunk identities, content hashes, and index settings,
  retires obsolete document points, and supports candidate promotion/rollback through Qdrant aliases;
- bounded generation context, OpenAI-compatible local generation, Pydantic JSON parsing, citation,
  quote-span and tax-year validation, explicit application statuses, and safe abstention;
- unit/integration evaluation utilities and an opt-in live retrieval benchmark harness.
- FastAPI retrieval, reranking, query, health/version, and process-local observability endpoints.
- Next.js UI with English, Norwegian Bokmål and Spanish labels, requested answer language,
  four-stage retrieval comparison, and opt-in inspection of the actual final answer context.
- Opt-in operator settings for saved model/Qdrant connections, dependency checks, and safe
  start/stop of preconfigured services on the API host.

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

The Python test suite does not require a GPU or live model server. Managed external runtimes
require weights installed beforehand. The optional in-process sentence-transformers adapters may
fetch missing weights on first inference; prepare their cache/offline settings separately.

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
uv run taxguide crawl --source skatteetaten-tax-return-en --max-pages 25 --max-depth 2
uv run taxguide corpus build --url-prefix "/en/person/taxes/" --language en --dry-run
uv run taxguide corpus build --url-prefix "/en/person/taxes/" --language en --index
```

Compare retrieval modes against the same indexed collection:

For annual amounts, first acquire and index annual rate pages: ordinary guidance URLs usually
have no verified tax year. Follow [annual corpus and build performance](docs/annual-corpus.md).
Build reports include verified document-year counts and stage timings. Local Qdrant/Ollama use
`127.0.0.1` in `configs/base.yaml` to avoid Windows localhost/IPv6 connection fallback delays.

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

With the same external services running, start the loopback-only API:

```bash
uv run uvicorn taxguide.api.app:app --host 127.0.0.1 --port 8000
```

See [HTTP API and observability](docs/api.md) for requests, configuration, tracing, metrics, and
security boundaries. Do not expose the unauthenticated API to the public Internet.

### Open the app

With the API running, open another terminal (Node.js 20.9+ required; Node 24 used in CI):

```console
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:3000**. No models are downloaded by the frontend. For a usable answer, first
prepare the indexed corpus and model services above. The default mode is dense; the inspector
requires the reranker as well. See the [frontend runbook](docs/frontend.md) for complete local
startup, errors and production builds, and [three-machine deployment](docs/three-machine-deployment.md)
to open the desktop-hosted app from the laptop through a private tunnel.

Open **http://127.0.0.1:3000/settings** for connections and local services. Administration is
disabled until the API has an operator key; executable/model paths must be configured in a trusted
local profile. Follow [runtime management](docs/runtime-management.md) for first-time setup.
“Local” means the Python API machine, not the browser machine. Model downloads and corpus indexing
remain manual; remote endpoints can be used and checked, but not remotely started or stopped.

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

The checked-in base configuration currently points the generator to the operator's remote
endpoint `http://100.112.6.87:8080`; embeddings, reranker and Qdrant remain local. The API host
must be able to reach that private address. For the all-local commands above, override
`generation.base_url` with `http://127.0.0.1:8080`. See [local runtime](docs/local-runtime.md).

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
src/taxguide/api/          HTTP boundary and observability
src/taxguide/runtime/      Operator connections and owned local-service lifecycle
frontend/                 Next.js UI and fixed-destination API proxy
```

## Verification

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Frontend checks (from `frontend/`):

```console
npm ci
npm run typecheck
npm run build
npx playwright install chromium
npm test
```

Browser tests run the production UI against a test-only HTTP upstream. Python tests independently
exercise HTTP → grounded service → prompt with injected model doubles. These checks do not replace
live corpus/model evaluation.

The live retrieval benchmark and grounded-generation smoke test are opt-in and require a populated
Qdrant collection plus the configured model services. See [retrieval](docs/retrieval.md) and
[grounded generation](docs/generation.md). No reproducible real-corpus baseline is committed yet.
Candidate indexing, live evaluation artifacts, and reviewed alias promotion/rollback are described
in [index lifecycle](docs/index-lifecycle.md).
Named crawl scopes live in [configs/sources.yaml](configs/sources.yaml); URL-only crawls remain
available under the host/path policy in `configs/base.yaml`. See [crawler](docs/crawler.md).

## Current limitations and next milestone

- Model installation/downloads, corpus indexing, and remote service startup remain operator steps.
  Optional local start/stop requires trusted profiles and one API worker.
- The UI is local/private. Only runtime administration has operator authentication; query endpoints
  remain unauthenticated. There is no chat persistence or public deployment.
  Requested answer language is a prompt instruction, not a verified translation; deterministic
  clarification/abstention text remains English and source excerpts are never translated.
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
- Query endpoints have no authentication or rate limiting. There is no distributed tracing
  exporter; operator dependency probes are basic checks, not end-to-end readiness guarantees.
  Bind to loopback or use an authenticated private gateway.
- TaxGuide provides information from official evidence; it is not a substitute for professional
  tax advice or an eligibility determination.

The next coherent milestones are the persistent role-aware embedding cache and reproducible real
retrieval/generation benchmarks. See [grounded generation](docs/generation.md) for the implemented
contract and its remaining limitations.

## Documentation

- [Architecture](docs/architecture.md)
- [Open the app: frontend runbook](docs/frontend.md)
- [HTTP API and observability](docs/api.md)
- [Local runtime and hardware](docs/local-runtime.md)
- [Connections and local-service controls](docs/runtime-management.md)
- [Desktop, laptop, and Oracle deployment](docs/three-machine-deployment.md)
- [Grounded generation status](docs/generation.md)
- [Crawler](docs/crawler.md)
- [Corpus workflow](docs/corpus.md)
- [Retrieval and evaluation](docs/retrieval.md)
- [Candidate index lifecycle](docs/index-lifecycle.md)
- [Tax routing](docs/routing.md)
- [Reranker service](docs/reranker-service.md)
- [Architecture reference](Design/norway_tax_rag_architecture.md)
