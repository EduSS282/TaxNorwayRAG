# ADR 0015: Private readiness controls and release evidence

Status: accepted, 2026-09-28.

## Context

The application has local RAG orchestration, but production-readiness tasks include PII-safe
logging, prompt injection, regression checks, deployment and a real benchmark. Those are
different trust boundaries; a passing unit suite is not proof of fiscal accuracy.

## Decision

- Remove raw paths, URLs and exception text from application INFO/WARNING crawler/source logs.
  Keep trace IDs and low-cardinality stage metrics without question/answer bodies. Disable
  Uvicorn's separate unsanitized access log in documented and container startup commands.
- Exclude high-confidence instructional markers from retrieved chunks before context selection.
  JSON-encode the remaining evidence in the prompt. Keep exact unmodified chunk text for citation
  validation and abstain if filtering leaves insufficient evidence.
- Add an explicit offline regression comparison between two candidate-bound retrieval artifacts
  with the same gold dataset version. Tolerances are operator choices, not universal release
  targets. The CI suite exercises the comparison with synthetic fixtures only.
- Provide a loopback-bound single-host Compose deployment for API, frontend and Qdrant; Ollama,
  llama.cpp, model downloads and networking remain operator managed.
- Require a reviewed corpus, gold judgments, model/hardware manifest, live retrieval and
  generation results, and human sign-off before calling a release production ready.

## Consequences

These controls lower accidental leakage and obvious injection risk, but neither establishes
semantic faithfulness. The initial regression gate covers retrieval only; a generation-quality
gate needs reviewed semantic judgments and real model outputs. The Docker deployment is private,
not an authenticated public service. No benchmark result is invented when services are offline.
