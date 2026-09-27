You are working on TaxGuide Norway.

Implement application/CLI composition for the retrieval components that already
exist in the repository.

IMPORTANT:
- Inspect the repository before making changes.
- Read AGENTS.md.
- Read the existing retrieval/reranking implementations and their tests first.
- Use norway_tax_rag_architecture.md ONLY as a design reference for this issue.
- Do NOT treat norway_tax_rag_architecture.md as a request to implement the
  whole architecture.
- Work ONLY on wiring/composition/configuration of the existing retrieval and
  reranking components.
- Do not reimplement algorithms that already exist.

==================================================
CURRENT STATE
==================================================

The current CLI:

    taxguide retrieve

only builds:

    DenseRetriever(create_embedder(settings.corpus), qdrant_store)

So the current runtime path is:

    query
      -> configured Embedder
      -> DenseRetriever
      -> Qdrant
      -> top-k

The repository already contains components including:

    src/taxguide/retrieval/dense.py
    src/taxguide/retrieval/sparse.py
    src/taxguide/retrieval/hybrid.py
    src/taxguide/reranking/qwen.py

but SparseRetriever, HybridRetriever and QwenReranker are not currently wired
into the CLI/application composition.

The existing QwenReranker currently uses sentence-transformers/CrossEncoder.

==================================================
GOAL
==================================================

Allow the existing `taxguide retrieve` command to explicitly run:

    dense
    sparse
    hybrid
    reranked

so we can manually compare retrieval quality using the same corpus and queries.

Desired CLI UX conceptually:

    taxguide retrieve "query" --mode dense
    taxguide retrieve "query" --mode sparse
    taxguide retrieve "query" --mode hybrid
    taxguide retrieve "query" --mode reranked

Default mode should remain:

    dense

to preserve backward compatibility.

For reranked mode, retrieve a larger candidate set first and rerank it to the
requested final limit.

Conceptually:

    query
         ┌──────── DenseRetriever ────────┐
         │                                │
         └──────── SparseRetriever ───────┤
                                          ↓
                                      fusion
                                          ↓
                                     top N candidates
                                          ↓
                                      reranker
                                          ↓
                                      final top K

However, inspect the actual existing HybridRetriever and reranker APIs and use
their current abstractions rather than forcing this exact pseudocode.

==================================================
1. INSPECT EXISTING COMPONENTS FIRST
==================================================

Before implementation, inspect:

- DenseRetriever
- SparseRetriever
- HybridRetriever
- RRF/fusion implementation
- Reranker protocol/interface if present
- QwenReranker
- ScoredChunk/domain models
- existing retrieval config
- existing tests
- existing evaluation code

Determine:

- how SparseRetriever obtains/indexes/searches its corpus
- how HybridRetriever expects dense/sparse retrievers to be supplied
- how fusion is configured
- how QwenReranker expects query/candidates
- whether a reranking wrapper/pipeline already exists

Reuse these implementations.

Do NOT create parallel implementations of BM25, RRF, dense retrieval or
reranking if they already exist.

==================================================
2. ADD RETRIEVAL MODE
==================================================

Extend `taxguide retrieve` with:

    --mode

Typed allowed values:

    dense
    sparse
    hybrid
    reranked

Prefer Literal or Enum consistent with project conventions.

Default:

    dense

Existing commands without --mode must continue behaving exactly as before.

Example:

    uv run taxguide retrieve \
      "Can I deduct childcare expenses from my taxes?" \
      --mode dense \
      --limit 5

==================================================
3. APPLICATION COMPOSITION
==================================================

Do not put all composition logic directly into the Typer command.

Create a clean factory/composition root for retrieval.

Conceptually something like:

    create_retriever(settings, mode, ...)

or an equivalent design consistent with the repository.

The CLI should not contain detailed provider-specific or algorithm-specific
construction logic.

Reuse:

    create_embedder(...)

for dense query embeddings.

Do not instantiate QwenEmbedder directly.

==================================================
4. DENSE MODE
==================================================

Dense mode must preserve current behavior:

    configured embedder
       -> QdrantVectorStore
       -> DenseRetriever

Do not change dense retrieval scoring or behavior.

This is our current baseline.

==================================================
5. SPARSE MODE
==================================================

Wire the EXISTING SparseRetriever into the application.

Important:
- Inspect how the existing SparseRetriever stores/loads its searchable corpus.
- Do not invent a second sparse implementation.
- Do not silently scan and rebuild the whole raw corpus for every query unless
  that is explicitly how the existing implementation was designed.
- If sparse retrieval requires initialization/index persistence that is
  currently missing from the application layer, implement only the minimal
  composition/persistence necessary to make the existing component usable.

Keep this issue focused.

==================================================
6. HYBRID MODE
==================================================

Wire the EXISTING HybridRetriever and existing fusion/RRF implementation.

Hybrid mode should combine the existing dense and sparse retrieval paths.

Do not implement a new fusion algorithm if RRF already exists.

Preserve scores/ranks according to the existing HybridRetriever contract.

The same query and final `--limit` must be usable across dense, sparse and
hybrid modes for comparison.

==================================================
7. RERANKED MODE
==================================================

Wire the existing QwenReranker.

Do not alter QwenReranker's scoring algorithm/model implementation unless a
small compatibility change is strictly necessary.

Reranked mode should NOT retrieve only `limit` candidates and rerank those same
few results.

Use a larger candidate pool.

Add a CLI/configurable option such as:

    --candidate-limit

with a sensible default, preferably 20 or the existing project-configured
value.

Constraints:

    candidate_limit >= limit

Conceptual behavior:

    hybrid retrieve top candidate_limit
        -> QwenReranker
        -> final top limit

Use hybrid candidates for reranked mode unless the existing architecture/tests
clearly define a different intended pipeline.

If the repository already contains a reranked retrieval pipeline, reuse it.

==================================================
8. RERANKER CONFIGURATION
==================================================

The current QwenReranker is local and uses sentence-transformers/CrossEncoder.

Make this explicit in configuration.

Do NOT implement an Ollama reranker adapter in this issue.

A reasonable configuration, adapted to existing config structure, would be:

retrieval:
  default_mode: dense
  candidate_limit: 20

  reranker_model: Qwen/Qwen3-Reranker-0.6B

or equivalent.

Do not hardcode the model name in the CLI if configuration already has an
appropriate place for it.

IMPORTANT:

The reranker must only be instantiated when reranking is requested.

Running:

    --mode dense
    --mode sparse
    --mode hybrid

must NOT load sentence-transformers CrossEncoder or download the reranker.

Only:

    --mode reranked

should initialize QwenReranker.

There must be NO silent fallback if reranker loading fails.

Return a useful error.

==================================================
9. OUTPUT
==================================================

Keep the current human-readable output style, but make the mode visible.

For example:

    mode=hybrid

    1. score=...
       source=...
       ...

For reranked results, show the final reranker score according to the existing
ScoredChunk/result model.

If useful and easy with existing models, optionally expose original retrieval
rank/score, but do NOT redesign the domain model solely for CLI cosmetics.

The core requirement is that the final ranking is clearly observable.

==================================================
10. COLLECTION / EMBEDDING CONSISTENCY
==================================================

Dense and hybrid modes must use the same configured embedding backend/model
used to build the Qdrant collection.

Continue using:

    create_embedder(settings.corpus)

Do not introduce a separate embedding configuration for retrieval.

Do not hardcode:

    Qwen/Qwen3-Embedding-0.6B

inside the retrieve CLI.

==================================================
11. ERROR HANDLING
==================================================

Provide useful errors for cases such as:

- unsupported mode
- sparse retriever cannot initialize
- hybrid component cannot initialize
- candidate_limit < limit
- reranker dependency unavailable
- reranker model cannot load
- Qdrant unavailable
- embedding backend unavailable

Do not silently switch retrieval modes when one component fails.

For example:

hybrid failure must NOT silently become dense retrieval.

==================================================
12. TESTS
==================================================

Tests must not require:

- internet
- Hugging Face
- real Ollama
- real Qdrant
- downloading a reranker model

Mock/fake all external/model dependencies.

Add tests covering at least:

1. default mode is dense
2. --mode dense uses DenseRetriever
3. --mode sparse uses existing SparseRetriever
4. --mode hybrid uses existing HybridRetriever
5. --mode reranked invokes reranking
6. reranked mode retrieves candidate_limit candidates
7. reranked mode returns only final `limit`
8. candidate_limit < limit is rejected
9. dense mode does NOT instantiate QwenReranker
10. sparse mode does NOT instantiate QwenReranker
11. hybrid mode does NOT instantiate QwenReranker
12. reranked mode DOES instantiate configured reranker
13. dense/hybrid use create_embedder/configuration
14. current retrieve behavior without --mode remains compatible
15. reranking changes order when fake reranker provides a different ranking
16. failures are surfaced rather than silently falling back

Preserve all existing retrieval/reranking tests.

==================================================
13. DOCUMENTATION
==================================================

Update the relevant retrieval documentation.

Document examples such as:

Dense:

    uv run taxguide retrieve \
      "Do I have to pay tax if I sell my home?" \
      --mode dense \
      --limit 5

Sparse:

    uv run taxguide retrieve \
      "Do I have to pay tax if I sell my home?" \
      --mode sparse \
      --limit 5

Hybrid:

    uv run taxguide retrieve \
      "Do I have to pay tax if I sell my home?" \
      --mode hybrid \
      --limit 5

Reranked:

    uv run taxguide retrieve \
      "Do I have to pay tax if I sell my home?" \
      --mode reranked \
      --candidate-limit 20 \
      --limit 5

Explain that the current Qwen reranker uses local
sentence-transformers/CrossEncoder and may download/load:

    Qwen/Qwen3-Reranker-0.6B

when reranked mode is first used.

Do NOT imply that the reranker runs through Ollama.

==================================================
14. NON-GOALS
==================================================

Do NOT:

- rewrite DenseRetriever
- rewrite SparseRetriever
- rewrite HybridRetriever
- rewrite RRF
- replace QwenReranker
- implement an Ollama reranker
- change embedding models
- change Qdrant indexing
- change chunking
- change parsing
- change crawler
- implement generation
- implement context building
- implement citations
- implement API/UI
- modify corpus scope
- fine-tune models

This issue is about composing and exposing already implemented retrieval
components.

==================================================
15. MANUAL ACCEPTANCE TARGET
==================================================

After implementation these commands should all work independently:

    uv run taxguide retrieve \
      "Can I deduct childcare expenses from my taxes?" \
      --mode dense \
      --limit 5 \
      --collection taxguide_chunks_ollama_qwen3_06b

    uv run taxguide retrieve \
      "Can I deduct childcare expenses from my taxes?" \
      --mode sparse \
      --limit 5 \
      --collection taxguide_chunks_ollama_qwen3_06b

    uv run taxguide retrieve \
      "Can I deduct childcare expenses from my taxes?" \
      --mode hybrid \
      --limit 5 \
      --collection taxguide_chunks_ollama_qwen3_06b

    uv run taxguide retrieve \
      "Can I deduct childcare expenses from my taxes?" \
      --mode reranked \
      --candidate-limit 20 \
      --limit 5 \
      --collection taxguide_chunks_ollama_qwen3_06b

Adapt these examples only if the existing SparseRetriever architecture makes a
Qdrant collection irrelevant for sparse-only mode.

==================================================
16. VALIDATION
==================================================

Before finishing run:

    uv run pytest
    uv run ruff check .
    uv run mypy src

Fix regressions caused by this issue.

Finally report:

- existing components discovered
- files added
- files modified
- exact runtime pipeline for each mode
- configuration added/changed
- whether sparse retrieval requires persisted state
- how hybrid composition works
- how many candidates are sent to reranker
- when the reranker model is instantiated
- tests added
- pytest result
- Ruff result
- mypy result
- known limitations

Do not continue to another issue.