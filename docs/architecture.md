# Current architecture

This document describes the code that exists in the repository. The broader target architecture
and future experiments live in `Design/norway_tax_rag_architecture.md`; their presence there does
not mean they are implemented.

## System boundary

TaxGuide owns deterministic acquisition, document processing, retrieval composition, tax-aware
routing, and grounded-generation contracts. Qdrant, Ollama, llama.cpp, and optional HTTP model
services are separate processes. TaxGuide connects to them but does not install models, start
services, create tunnels, or manage their lifecycle.

The current user-facing boundary ends at retrieval:

```text
taxguide crawl    → saved HTML + crawl manifests
taxguide corpus   → normalized/chunked corpus, optionally indexed
taxguide retrieve → ranked chunks
```

There is no `taxguide answer` command, generation API, or service that composes the complete RAG
path yet.

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

Qdrant collection creation and vector-schema validation are not implemented. Operators must
create a collection compatible with the selected embedding dimension before indexing.

## Deterministic query routing

The routing layer is independent from the retrieval CLI and generation components. It combines:

- a closed multilingual individual-tax taxonomy;
- rule-based intent classification;
- deterministic risk classification;
- a route decision: `retrieve`, `clarify`, or `abstain`;
- controlled topic/audience/source/year filters and a minimum-evidence requirement.

The router does not infer residency, eligibility, or a missing tax year, and it does not generate
tax advice. High-risk or year-sensitive questions without a resolved year require clarification.
The future grounded service must explicitly compose this layer; merely having the router module
does not apply it to `taxguide retrieve`.

## Grounded-generation primitives

The following components are implemented and independently tested:

- `ContextBuilder`, which selects ranked, unique chunks within a declared chunk-token budget;
- `RagAnswer` and `Citation`, which define structured output;
- `build_grounded_messages`, which supplies evidence IDs and a JSON schema;
- `OpenAICompatibleGenerator`, which calls `/v1/chat/completions`;
- `CitationValidator`, which checks evidence ID, chunk ID, URL, title, and duplicate chunks;
- `AbstentionPolicy`, which produces a canonical non-claiming response;
- retrieval and generation evaluation models and metrics.

They are not composed into an application service. The configuration names a generator model but
does not contain a provider endpoint or timeout, and no factory constructs a generator. Generated
text is not parsed into `RagAnswer` by an application path. Quote spans are structurally validated
but are not checked against source text. Context token accounting covers chunk tokens, not rendered
metadata or prompt/schema overhead.

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
Ollama for embeddings, llama.cpp for the optional reranker and future generator, and loopback-only
model endpoints. A remote VM is suitable for crawling, scheduled work, backups, or a secured
Qdrant service, but not required for local development. See [local runtime](local-runtime.md) and
ADR 0005.

## Known architectural gaps

The next milestone should close these gaps together rather than presenting individual generation
classes as a finished RAG system:

1. create/validate the Qdrant collection and embedding dimension;
2. add generator endpoint configuration and a generator factory;
3. compose router, temporal resolution, retrieval, reranking, context, generation, parsing,
   validation, and abstention in `GroundedRagService`;
4. expose an `answer` CLI entry point with explicit answered/abstained/failed status;
5. validate quote spans, tax-year consistency, and untrusted evidence handling;
6. add deterministic and live end-to-end tests;
7. integrate a role-aware persistent embedding cache;
8. establish real, versioned retrieval and generation baselines.
