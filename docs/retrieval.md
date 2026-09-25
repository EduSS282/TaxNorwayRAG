# Retrieval modes

`taxguide retrieve` compares the same indexed corpus through four explicit modes.
The default remains `dense`.

```bash
uv run taxguide retrieve "Do I have to pay tax if I sell my home?" --mode dense --limit 5
uv run taxguide retrieve "Do I have to pay tax if I sell my home?" --mode sparse --limit 5
uv run taxguide retrieve "Do I have to pay tax if I sell my home?" --mode hybrid --limit 5
uv run taxguide retrieve "Do I have to pay tax if I sell my home?" --mode reranked --candidate-limit 20 --limit 5
uv run taxguide retrieve "What is the minimum standard deduction?" --tax-year 2025 --mode hybrid --limit 5
```

Dense retrieval embeds the query with the configured embedding provider and searches Qdrant.
Sparse retrieval loads the persisted chunk payloads from the configured Qdrant collection once,
then builds the existing in-memory BM25 index. Hybrid retrieval fuses dense and sparse rankings
with reciprocal-rank fusion. Reranked retrieval obtains `candidate_limit` hybrid candidates (10 by
default), then returns the requested final limit after Qwen reranking. `candidate_limit` must be at
least `limit`.

`--tax-year` accepts years from 1900 through 2100. When supplied, all modes use strict
`metadata.tax_year == requested_year` matching: Qdrant applies it before dense ranking, and the
in-memory sparse index applies it before lexical ranking. Chunks without a tax year are therefore
not included in a year-filtered result set.

If the query itself mentions one year, the CLI resolves it automatically and applies the same
pre-ranking filter. An explicit `--tax-year` that conflicts with the query is rejected, as is a
query containing multiple distinct years. Higher application layers can provide conversation,
identified-form, and current-applicable-year hints through `TaxYearResolutionContext`; precedence
is explicit query, conversation, form, then current year. `GroundedRagService` accepts an injected
`tax_year_context_provider(question)` for those trusted application hints. Its default is empty,
so a year-sensitive grounded answer asks for clarification unless the query or caller supplies a
year. A context that marks the year as required also asks for clarification before retrieval when
no year resolves; it never silently selects one.

`TaxYearAwareRetriever` also validates returned payloads. A vector-store or retriever adapter that
ignores the filter and returns a different or unknown year raises `CrossYearRetrievalError`, so
wrong-year evidence cannot reach reranking or generation. Qdrant translates every declared
metadata filter (`tax_year`, `language`, `source`, `document_type`, `audience`, and `topic`) into
`must` conditions before dense search.

The reranker is only constructed in `reranked` mode. Set `retrieval.reranker_provider` to `local`
for the local `sentence-transformers` `CrossEncoder`, or `http` for a remote service. Both preserve
the raw model score, including negative logits; scores are rankings rather than probabilities. The
configured model is `Qwen/Qwen3-Reranker-0.6B`. See [reranker service](reranker-service.md) for
remote-service setup.

## Live retrieval benchmark

The live harness expects a local gold set at `data/evaluation/retrieval_gold_v1.json` and matches
results by normalized source URL (scheme/host case, query, fragment, and a trailing slash are
ignored). The `data/` directory is ignored by Git, so a fresh checkout does not contain this real
evaluation corpus and the repository does not yet publish a reproducible baseline. The harness
compares dense,
sparse, hybrid, and reranked retrieval with Recall@1/5/10, MRR, graded nDCG@5/10, and latency.
Repeated chunks from one source URL count as a single document at their first retrieved position;
all metric cutoffs apply after this stable URL deduplication. Latency includes cold initialization,
including the first embedding request, so the report represents end-to-end user-visible timing.
The reranked pipeline evaluates 10 candidates but returns only 5 results, so its R@10 and nDCG@10
cells are reported as `n/a`. Success@1/5 reports the fraction of queries with at least one relevant
source at the cutoff. The live output also lists queries where Hybrid@5 found a relevant source but
reranking moved its first relevant source lower or out of the final five.

Set `TAXGUIDE_RETRIEVAL_EVAL_COLLECTION` to evaluate a physical candidate instead of the configured
collection, and `TAXGUIDE_RETRIEVAL_EVAL_REPORT` to save a JSON artifact bound to that collection
and gold-dataset version. This artifact is the evidence accepted by index promotion; it does not
certify quality or choose release thresholds.

It is intentionally excluded from normal tests. With a populated configured Qdrant collection and
the configured embedding and reranker services available, run:

```bash
TAXGUIDE_RUN_RETRIEVAL_EVAL=1 uv run pytest -m retrieval_eval -s
```

The benchmark never starts services, downloads models, or creates SSH tunnels.

Promotion requires reviewing the candidate-bound artifact and explicitly passing
`--evaluation-passed`. The command checks the collection name and presence of Dense, Sparse,
Hybrid, and Hybrid+Reranker rows, then atomically updates the stable Qdrant aliases. See
[index lifecycle](index-lifecycle.md) for the workflow and its limitations.

Results are exploratory until the gold set, corpus manifest, model revisions/quantizations,
hardware/runtime manifest, thresholds, and generated report are versioned together. The small
checked-in fixtures under `tests/fixtures/evaluation/` test metric contracts; they are not evidence
of real retrieval or generation quality.
