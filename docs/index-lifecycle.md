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
candidate skips embedding only when the exact chunk IDs, content hashes, and parse/chunk/embed
settings signature match. A changed source hash creates a new version. Once all new point writes
complete, the builder removes obsolete points for that document; dense and sparse readers of that
collection then see only the current version. An interrupted write can temporarily expose a mix
of versions until the next successful build, so production readers should use the active alias and
build candidates separately. The signature does not capture immutable upstream model weights or
library revisions; use a fresh candidate if those change. Candidates must use a compatible
collection schema and be evaluated with the intended embedder.

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
read through the alias. On first promotion, if no current alias exists and the configured
`corpus.qdrant_collection` is an existing physical collection distinct from the candidate, it is
adopted as `taxguide_previous` in the same alias update. This preserves one-step rollback from a
pre-alias deployment. If that collection does not exist, there is no prior index to roll back to.
After promotion, set reader configuration to `taxguide_current`; keep a separate physical target
for candidate builds.

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
- Sparse retrieval loads payloads from the configured collection, so it follows the alias when
  configured to use `taxguide_current`; in-process lexical snapshots need refreshing after a swap.
- Evaluation artifacts bind results to collection and dataset version but do not yet capture
  immutable model revisions, runtime versions, or hardware details.
- The benchmark is exploratory until a representative gold set and reviewed thresholds are
  maintained with the corpus and environment manifest.
- `taxguide_current` and `taxguide_previous` must be reserved for aliases, not physical collection
  names. Existing consumers must be configured to query the active alias to receive promotions.
