# Exploratory v1 retrieval measurement — 2026-09-28

This is a **real-service retrieval run**, not an approved v1 release baseline. The machine ran
30 questions against the populated Qdrant collection, Ollama embedding service and a CPU-hosted
llama.cpp reranker. The raw [four-pipeline artifact](retrieval-v1-2026-09-28.json) is retained
for reproducibility; it must not be used as `--evaluation-passed` without reviewing the gold
judgments and corpus snapshot.

## Inputs and environment

- Gold set: `data/evaluation/retrieval_gold_v1.json`, version `v1`, 30 queries, 24 distinct
  relevant URLs; SHA-256 `1B9B268F529511FDC5EB28EB1DDF5372126868927B6E4A409D243392A6E5A5CD`.
- Qdrant `v1.19.0`: physical collection `taxguide_chunks_temporal_v1`, green, 2,978 points,
  449 distinct source URLs, 1,024-dimensional cosine vectors. All 24 gold URLs were present.
  The points carried one index signature:
  `c0b20fd722b5b48b72ca1e5f364b69a7191795663022a904f4f20f0f2455e161`.
- Embedding: Ollama `0.34.4`, `qwen3-embedding:0.6b` (local model ID `ac6da0dfba84`).
  Reranking: llama.cpp build `11216`, `Qwen3-Reranker-0.6B-Q8_0`, CPU (`-ngl 0`), 10
  candidates, context 4,096, physical batch 2,048.
- Host: Windows, Intel Core i7-13700H, 15.7 GiB RAM. The run used the opt-in
  `configs/evaluation-cpu.yaml` timeout of 180 seconds, **not** the application's normal
  30-second reranker timeout. The harness was run from the revision committed with this report;
  the collection was not snapshotted or frozen against concurrent writes.

## Observed aggregate results

| Pipeline | Recall@1 | Recall@5 | Recall@10 | nDCG@5 | Mean latency | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dense | 0.133 | 0.733 | 0.800 | 0.462 | 0.248 s | 0.621 s |
| Sparse | 0.167 | 0.367 | 0.433 | 0.268 | 0.020 s | 0.025 s |
| Hybrid | 0.300 | 0.600 | 0.700 | 0.470 | 0.278 s | 0.609 s |
| Hybrid + Reranker | 0.300 | 0.600 | n/a | 0.457 | 34.789 s | 52.486 s |

The reranker did **not** improve Recall@5 over Hybrid; its MRR was 0.409 versus Hybrid's
0.438. The diagnostic output showed relevant-source demotions for at least `childcare-en`,
`home-sale` and `advance-tax`. Its median latency was 32.536 seconds, above the normal
30-second HTTP timeout, so this CPU deployment cannot be treated as a reliable default for
Hybrid + Rerank. Dense had the highest Recall@5 on this small set, while Hybrid had the highest
Recall@1. Each question currently has only one gold URL, so these figures do not measure full
answer evidence coverage or graded agreement among multiple sources. The saved artifact contains
aggregate rows, not the per-question rankings printed during the run; the three examples above
are leads for a repeat diagnostic, not independently reviewable evidence.

## Release decision and missing evidence

**Not ready for v1 approval.** The 30 judgments are preliminary and have not been independently
reviewed against current official pages or year applicability. There is no immutable corpus
snapshot or reviewed historical baseline for a regression comparison. The configured remote
generator was unavailable, so no live grounded-generation scores, citation/faithfulness review,
numerical/year review or adversarial review were produced. Re-run on the intended deployment
hardware, review failures case by case, freeze the corpus/model revisions, and obtain human
sign-off before treating this artifact as a release gate.
