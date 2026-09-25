# Current architecture

This document describes the code that exists in the repository. The broader target architecture
and future experiments live in `Design/norway_tax_rag_architecture.md`; their presence there does
not mean they are implemented.

## System boundary

TaxGuide owns deterministic acquisition, document processing, retrieval composition, tax-aware
routing, and grounded-generation contracts. Qdrant, Ollama, llama.cpp, and optional HTTP model
services are separate processes. TaxGuide connects to them but does not install models, start
services, create tunnels, or manage their lifecycle.

The current CLI boundary includes grounded generation:

```text
taxguide crawl    → saved HTML + crawl manifests
taxguide corpus   → normalized/chunked corpus, optionally indexed
taxguide retrieve → ranked chunks
taxguide answer   → validated answer, clarification, abstention, or failure
```

There is no HTTP API or frontend. External model and vector processes remain operator-managed.

## Offline pipeline

```text
Skatteetaten URL
  → SkatteetatenCrawler
  → raw HTML + CrawlManifest
  → ManifestCorpusSelector
  → LocalHtmlSource
  → SkatteetatenHtmlParser
  → Normalizer
  → fixed | recursive | structural chunker
  → optional Embedder
  → QdrantVectorStore
```

The crawler is bounded by host/path allowlists, robots rules, depth, page count, response size,
retry policy, and delay. Raw HTML and its manifest are stored separately. Corpus selection uses
manifests rather than filenames, excludes failed/non-HTML captures, and can exclude duplicate or
interactive-wizard pages.

`RawDocument → ParsedDocument → Document` separates source capture, extraction, and cleanup.
Documents and chunks retain source URL, local path, retrieval timestamp, content hash, language,
and temporal applicability where it is known.

## Identity and temporal data

- `document_id` is derived from the canonical source URL.
- `version_id` is derived from `document_id + content_hash`.
- chunk identity includes the document version, section path, and chunk index.
- `tax_year`, `valid_from`, and `valid_to` remain independent optional facts; one is never inferred
  from another.
- temporal metadata is copied into every chunk and persisted in the Qdrant payload.

The corpus builder can derive a tax year from an explicit version URL. Missing temporal knowledge
stays missing. See ADR 0004 for the versioning decision.

## Retrieval pipeline

```text
query
  → TaxYearResolver
  → RetrievalFilter
  → dense ───────────────┐
     sparse (BM25) ──────┼→ reciprocal-rank fusion → optional reranker
                         └→ ranked ScoredChunk values
  → TaxYearAwareRetriever result validation
```

Four explicit modes are composed by `retrieval.factory.create_retriever`:

- **dense** embeds the query and searches the configured Qdrant collection;
- **sparse** loads stored chunk payloads and builds an in-memory BM25 index;
- **hybrid** fuses dense and sparse ranks with reciprocal-rank fusion;
- **reranked** sends hybrid candidates to a local, HTTP, or llama.cpp Qwen reranker.

Metadata constraints are applied before dense ranking in Qdrant and before sparse ranking in
memory. `TaxYearAwareRetriever` also rejects missing or mismatched years returned by an adapter,
preventing cross-year evidence from reaching later stages.

An indexed corpus build asks the embedder for its dimension, creates a missing cosine collection,
and validates the size/distance of an existing collection before upsert. Named-vector collections
are intentionally rejected by the current single-vector adapter.

## Deterministic query routing

The routing layer is independent from the retrieval CLI and generation components. It combines:

- a closed multilingual individual-tax taxonomy;
- rule-based intent classification;
- deterministic risk classification;
- a route decision: `retrieve`, `clarify`, or `abstain`;
- controlled topic/audience/source/year filters and a minimum-evidence requirement.

The router does not infer residency, eligibility, or a missing tax year, and it does not generate
tax advice. High-risk or year-sensitive questions without a resolved year require clarification.
`taxguide answer` composes the router before retrieval. The lower-level `taxguide retrieve` command
continues to apply temporal resolution and caller-supplied filters directly, without intent/risk
routing.

## Grounded-generation pipeline

`GroundedRagService` composes the implemented components in a fail-closed path:

- `ContextBuilder`, which selects ranked, unique chunks within a declared chunk-token budget;
- `RagAnswer` and `Citation`, which define structured output;
- `build_grounded_messages`, which supplies evidence IDs and a JSON schema;
- `OpenAICompatibleGenerator`, which calls `/v1/chat/completions`;
- `CitationValidator`, which checks evidence ID, chunk ID, URL, title, and duplicate chunks;
- `AbstentionPolicy`, which produces a canonical non-claiming response;
- retrieval and generation evaluation models and metrics.

The service resolves a year from the query and an optional injected trusted context provider,
routes the question, retrieves and checks temporal evidence,
enforces the risk-dependent evidence count, builds context, calls the configured generator, parses
the response as `RagAnswer`, validates grounding, and returns an explicit status. Malformed JSON or
runtime failures return `failed`; insufficient or invalid grounding returns a canonical
`abstained` answer. A model cannot mark its own citations valid or lower evidence requirements.

Quote spans are validated against chunk bounds and must select non-blank text. The schema does not
include a copied quote, so semantic quote equality is not available. Context accounting covers
chunk tokens, not rendered metadata, the JSON schema, or chat-template overhead. Online validation
checks traceability, not claim-level semantic faithfulness.

See [grounded generation](generation.md) for the required orchestration and fail-closed contract.

## Embedding cache status

`CachingBatchingEmbedder` can batch missing texts and cache vectors in an injected mutable mapping.
It is not used by `embeddings.factory.create_embedder`, defaults to process memory, exposes no
metrics, and uses one text/model key shape for both document and query embeddings. It must not be
described as a persistent production cache.

## Evaluation status

Unit-tested utilities exist for Recall@K, MRR, nDCG, retrieval latency, citation precision/recall,
faithfulness, answer correctness, and abstention accuracy. The live retrieval test is opt-in and
depends on operator-managed services and data.

There is currently no checked-in real-corpus benchmark baseline with repeatable hardware/model
metadata and release thresholds. The checked-in generation evaluation fixture contains only two
contract-level cases. These tools validate interfaces but do not yet demonstrate production
quality.

## Dependency direction

```text
CLI/application composition → configuration + contracts + adapters
adapters                    → domain contracts
pipelines                   → injected interfaces
domain                      → standard library + Pydantic
```

External frameworks do not own the domain model or orchestration. Components remain replaceable
through explicit protocols and dependency injection; LangChain, LlamaIndex, and Haystack are not
used.

## Runtime topology

The supported development topology is local-first: TaxGuide and Qdrant on the primary workstation,
Ollama for embeddings, llama.cpp for the optional reranker and generator, and loopback-only
model endpoints. A remote VM is suitable for crawling, scheduled work, backups, or a secured
Qdrant service, but not required for local development. See [local runtime](local-runtime.md) and
ADR 0005.

## Known architectural gaps

The grounded CLI milestone is complete, but these gaps remain:

1. integrate a role-aware persistent embedding cache;
2. establish real, versioned retrieval and generation baselines with hardware/model manifests;
3. count complete rendered prompt tokens rather than only chunk tokens;
4. add a copied quote or claim mapping if exact semantic quote validation is required;
5. enrich corpus topic/audience metadata before applying every router filter to retrieval;
6. add authenticated HTTP/API deployment, observability, and service supervision;
7. execute and record the existing opt-in live smoke test on the target hardware and corpus.
