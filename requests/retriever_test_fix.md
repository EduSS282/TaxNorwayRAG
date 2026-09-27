You are working on TaxGuide Norway.

Fix the retrieval benchmark's URL-level metric semantics.

Current live benchmark failure:

    BenchmarkRow validation fails because:

        ndcg_at_10 = 1.1537637368822935

nDCG must be in [0, 1].

IMPORTANT:
- Inspect the existing evaluation code first.
- Read AGENTS.md.
- Work ONLY on retrieval benchmark metric correctness.
- Do not modify retrieval algorithms, embeddings, Qdrant, reranking, corpus,
  parsing or generation.
- Do NOT clamp nDCG to 1.
- Find and fix the mathematical/root semantic cause.

==================================================
CURRENT EVALUATION MODEL
==================================================

The benchmark retrieves chunks but evaluates relevance using normalized
source URLs.

Therefore several retrieved chunks may have the same source URL.

Example:

    rank 1 -> URL A / chunk 1
    rank 2 -> URL A / chunk 2
    rank 3 -> URL B / chunk 1

Gold relevance is URL-level:

    URL A -> relevance 3
    URL B -> relevance 2

A URL-level ranking metric must not award relevance multiple times merely
because several chunks from the same source document were retrieved.

This likely causes DCG to count the same relevant source URL multiple times,
while IDCG contains each gold URL only once, resulting in nDCG > 1.

==================================================
1. CONFIRM ROOT CAUSE
==================================================

Inspect:

    src/taxguide/evaluation/retrieval_benchmark.py
    src/taxguide/evaluation/metrics.py

and relevant tests.

Confirm exactly why nDCG can exceed 1.

Do not assume this explanation without inspecting the implementation.

Report the actual root cause.

==================================================
2. DEFINE URL-LEVEL RANKING SEMANTICS
==================================================

The current benchmark gold judgments are source-URL-level.

Therefore convert chunk retrieval rankings into unique source-URL rankings
before computing URL-level metrics.

Deduplicate retrieved URLs while preserving the first/highest-ranked
occurrence.

Example:

Input:

    [
      URL_A,
      URL_A,
      URL_B,
      URL_C,
      URL_B,
    ]

Evaluation ranking:

    [
      URL_A,
      URL_B,
      URL_C,
    ]

Do not reorder URLs beyond removing later duplicates.

Use the same normalized URL representation used for gold matching.

==================================================
3. APPLY CONSISTENTLY TO METRICS
==================================================

Ensure URL-level deduplication semantics are consistently used for:

    Recall@1
    Recall@5
    Recall@10
    MRR
    nDCG@5
    nDCG@10

Do not deduplicate only for nDCG while leaving inconsistent semantics in the
other URL-level metrics.

Important:
K should apply to the deduplicated URL ranking when evaluating URL-level
retrieval.

The production retriever still returns chunks unchanged.
This transformation is evaluation-only.

==================================================
4. NDCG CORRECTNESS
==================================================

Ensure:

    0 <= nDCG@k <= 1

for valid graded relevance judgments.

Use the project's existing gain/discount convention unless it is itself
incorrect.

IDCG must represent the best possible ordering of the UNIQUE gold relevance
judgments.

Do not duplicate a gold judgment.

If no relevant documents exist, follow the existing documented metric
convention, but benchmark dataset validation should normally prevent that.

==================================================
5. TESTS
==================================================

Add regression tests for at least:

A. Duplicate relevant URL:

Gold:
    A -> relevance 3
    B -> relevance 2

Retrieved:
    A, A, B

Expected evaluation ranking:
    A, B

nDCG must be <= 1 and ideally 1 for the correctly ordered unique ranking.

B. Duplicate lower-ranked URL:

Retrieved:
    B, B, A

Ensure deduplication preserves:
    B, A

and nDCG reflects that ordering.

C. Duplicate irrelevant URLs.

D. Recall@K with duplicate chunk URLs does not artificially change
document-level semantics.

E. MRR uses first unique relevant source correctly.

F. Every valid generated nDCG test satisfies:
    0 <= score <= 1

G. URL normalization happens before deduplication, so equivalent URLs differing
only by harmless trailing slash normalization are treated as the same source.

==================================================
6. OPTIONAL HELPER
==================================================

If appropriate, introduce a small explicit helper such as:

    unique_ranked_urls(...)

or equivalent.

Keep it generic and testable.

Do not embed this logic implicitly in multiple metrics.

==================================================
7. LATENCY NOTE
==================================================

Inspect the benchmark latency measurement.

The first dense query currently appears significantly slower than subsequent
queries, likely due to cold initialization:

    first query ~12.6 s
    subsequent queries ~0.3 s

Do NOT silently remove this timing.

If practical within this issue, clearly distinguish or document cold-start
latency versus steady-state latency, or perform one explicit unmeasured warm-up
before aggregate steady-state measurement.

Only do this if it can be done without broadening scope significantly.

Do not manipulate timings simply to make results look better.

==================================================
8. VALIDATION
==================================================

Run:

    uv run pytest
    uv run ruff check .
    uv run mypy src

Also run the relevant offline evaluation tests.

Do not require real external services for normal tests.

Finally report:

- confirmed root cause of nDCG > 1
- exact URL deduplication semantics
- metrics affected
- tests added
- whether latency handling changed
- pytest result
- Ruff result
- mypy result

Do not continue to another issue.