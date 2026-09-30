You are working on TaxGuide Norway.

Expose the existing tax_year retrieval filtering end-to-end through the
`taxguide retrieve` CLI.

IMPORTANT:
- Inspect the repository first.
- Read AGENTS.md.
- Use norway_tax_rag_architecture.md only as design reference.
- Work only on retrieval metadata-filter plumbing.
- Do not change retrieval algorithms, embeddings, RRF, reranking, Qdrant
  collection structure, temporal extraction, generation, or tax rules.

==================================================
CURRENT STATE
==================================================

The repository already contains:

    src/taxguide/retrieval/filters.py

with a model containing:

    tax_year: int | None

and filtering logic equivalent to:

    filters.tax_year is None or metadata.tax_year == filters.tax_year

Indexed Qdrant payloads now contain temporal metadata such as:

    metadata.tax_year = 2026

Example real payload:

    source_url:
    https://www.skatteetaten.no/en/rates/minimum-standard-deduction/?year=2026

    tax_year:
    2026

However:

    uv run taxguide retrieve --help

does NOT expose any --tax-year option.

==================================================
GOAL
==================================================

Support:

    uv run taxguide retrieve \
      "What is the minimum standard deduction for salary income?" \
      --tax-year 2025 \
      --mode dense \
      --limit 10 \
      --collection taxguide_chunks_temporal_v1

and equivalently for:

    sparse
    hybrid
    reranked

The requested tax year must constrain retrieval evidence.

==================================================
1. INSPECT EXISTING FILTER FLOW
==================================================

Trace filtering through:

    CLI
      -> create_retriever
      -> DenseRetriever
      -> SparseRetriever
      -> HybridRetriever
      -> reranked pipeline
      -> vector store / in-memory sparse corpus

Reuse existing MetadataFilter abstractions.

Do not create a second filtering system.

==================================================
2. CLI
==================================================

Add:

    --tax-year INTEGER

Requirements:

- optional
- valid range consistent with MetadataFilter
- when absent, preserve current behavior exactly
- when present, construct/use the existing retrieval filter model

Expected help output should include --tax-year.

==================================================
3. DENSE RETRIEVAL
==================================================

Ensure dense retrieval applies tax_year as a real vector-store metadata
filter when possible.

Do not:
- retrieve everything and filter after top-k if Qdrant can filter before
  ranking
- encode the year only into the natural-language query

The desired behavior is:

    semantic query
    +
    metadata.tax_year == requested year

==================================================
4. SPARSE RETRIEVAL
==================================================

Ensure sparse retrieval applies the same logical filter before producing its
ranked candidate set.

A 2025 request must not return a 2026 chunk merely because BM25 relevance is
high.

==================================================
5. HYBRID RETRIEVAL
==================================================

Dense and sparse branches must operate over the same requested temporal
subset before fusion.

Do not fuse wrong-year candidates and remove them only afterward unless the
existing architecture makes pre-filtering impossible.

==================================================
6. RERANKED MODE
==================================================

The reranker must receive only candidates compatible with the requested
tax_year.

Expected flow:

    query
      -> filtered dense+sparse retrieval
      -> fusion
      -> top candidate_limit
      -> reranker
      -> final top-k

The reranker must not be responsible for deciding fiscal year.

==================================================
7. YEAR-INDEPENDENT DOCUMENTS
==================================================

Inspect how temporal metadata currently represents year-independent guidance.

For this issue, do NOT invent complex fallback semantics.

Use the existing filter contract consistently.

If tax_year filtering currently means strict equality:

    metadata.tax_year == requested_year

preserve that unless there is already an explicit design for including
year-independent documents.

Document the behavior.

==================================================
8. TESTS
==================================================

Add fast offline tests covering at least:

- CLI accepts --tax-year 2025
- CLI accepts --tax-year 2026
- invalid years are rejected
- no --tax-year preserves previous behavior
- dense passes the filter correctly
- sparse honors the filter
- hybrid honors the filter
- reranked mode reranks only filtered candidates
- a 2025 query cannot return an explicitly 2026-only candidate
- a 2026 query cannot return an explicitly 2025-only candidate

Use fakes/mocks; normal tests must not require Qdrant/Ollama/llama.cpp.

==================================================
9. OPTIONAL QDRANT INTEGRATION TEST
==================================================

If the repository already has Qdrant integration-test conventions, add a
small opt-in test verifying that:

    metadata.tax_year == 2025

is translated to the correct Qdrant filter.

Do not make normal pytest depend on a running Qdrant instance.

==================================================
10. NON-GOALS
==================================================

Do not:
- infer tax year from query text
- implement temporal query understanding
- implement tax calculations
- implement fallback across years
- change temporal metadata extraction
- change scoring algorithms
- modify the reranker model

==================================================
11. VALIDATION
==================================================

Run:

    uv run pytest
    uv run ruff check .
    uv run mypy src

Then verify help:

    uv run taxguide retrieve --help

Expected:

    --tax-year

Finally report:

- files changed
- existing filter path discovered
- how dense filtering is applied
- how sparse filtering is applied
- hybrid/reranked behavior
- tests
- pytest result
- Ruff result
- mypy result

Do not continue to another issue.