# Candidate index lifecycle

The active retrieval index should not be overwritten while it is being rebuilt. Build into a
physical Qdrant collection, evaluate it against the local gold dataset, review the report, then
promote it through stable aliases. Alias updates are atomic in Qdrant, and one prior collection is
retained for a one-step rollback.

## 1. Build a candidate

Choose a fresh collection name for this evaluation cycle:

```console
uv run taxguide corpus build --url-prefix "/en/person/taxes/" --language en --index --collection taxguide_candidate_2026_09
```

The command creates and validates a single-vector cosine collection. Re-running against the same
candidate skips document versions already present. A changed source hash creates a new version;
the old points are retained. Candidates must be evaluated using the same embedder and compatible
collection schema as production.

## 2. Evaluate the candidate

The benchmark needs a curated `data/evaluation/retrieval_gold_v1.json`, candidate corpus, Qdrant,
the embedding service, and reranker service. For PowerShell:

```powershell
$env:TAXGUIDE_RUN_RETRIEVAL_EVAL = "1"
$env:TAXGUIDE_RETRIEVAL_EVAL_COLLECTION = "taxguide_candidate_2026_09"
$env:TAXGUIDE_RETRIEVAL_EVAL_REPORT = "data/evaluation/reports/candidate_2026_09.json"
uv run pytest -m retrieval_eval -s
```

The JSON report records the candidate collection, gold dataset version, timestamp and metrics for
Dense, Sparse, Hybrid, and Hybrid+Reranker. It is an evaluation record, not a quality guarantee.
No real-corpus gold set, hardware manifest, agreed thresholds, or accepted baseline is checked in
yet. A human must inspect quality and latency before explicitly approving promotion.

## 3. Promote

After reviewing the report and candidate, run:

```console
uv run taxguide index promote --candidate taxguide_candidate_2026_09 --evaluation-report data/evaluation/reports/candidate_2026_09.json --evaluation-passed
```

The command verifies that the report names the same candidate and contains all four pipeline rows.
The explicit `--evaluation-passed` flag records the operator's review decision. It does not compare
metrics to thresholds, because none are defined. By default, `taxguide_current` points at the new
collection and `taxguide_previous` retains the former active collection. Retrieval continues to
use the collection configured by the application; configure that setting to `taxguide_current` to
read through the alias.

## 4. Roll back

If post-promotion checks fail, swap the active and previous targets:

```console
uv run taxguide index rollback
```

The rollback alias then points to the collection that was active immediately before rollback, so
the operation can be repeated to switch back. Qdrant collections are not deleted by promotion or
rollback. There is no automatic candidate cleanup, retention policy, or garbage collection yet;
operators must ensure sufficient storage and remove obsolete collections deliberately.

## Scope and limitations

- This lifecycle changes Qdrant aliases only; it does not deploy models or restart application
  processes.
- Sparse retrieval currently loads payloads from a collection and needs no separate index alias.
- Evaluation artifacts bind results to collection and dataset version but do not yet capture
  immutable model revisions, runtime versions, or hardware details.
- The benchmark is exploratory until a representative gold set and reviewed thresholds are
  maintained with the corpus and environment manifest.
- `taxguide_current` and `taxguide_previous` must be reserved for aliases, not physical collection
  names. Existing consumers must be configured to query the active alias to receive promotions.
