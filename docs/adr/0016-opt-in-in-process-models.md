# ADR 0016: Keep local Python models opt-in

Status: accepted, 2026-09-28.

## Context

The private API container delegates embedding to Ollama and reranking to llama.cpp by default.
The mandatory `sentence-transformers` dependency nevertheless pulled PyTorch and CUDA libraries
into the API image, consuming gigabytes without serving these default requests.

## Decision

Move `sentence-transformers` to the `local-models` project extra. `uv sync --locked` installs
the external-provider runtime; `uv sync --locked --extra local-models` preserves the previous
in-process Qwen embedding/reranking behavior and the standalone Python reranker service. The
adapters remain importable and report a clear missing-extra error when selected without it.
The Docker API image uses the default set; no model provider or corpus schema changes.

## Migration and rollback

Existing local-provider operators add `--extra local-models` on the next sync. To roll back an
environment to the previous dependency set, run that same command; no data migration or index
rewrite is needed. To return to the smaller external-provider set, run `uv sync --locked`.
Do not switch an already-running in-process model service to the default set without changing
its configuration or stopping it. CI tests both package metadata and default-provider behavior.
