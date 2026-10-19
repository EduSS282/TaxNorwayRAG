# ADR 0018: Standalone host stack and native Vertex AI generation

## Status

Accepted.

## Context

A complete Linux VM demonstration should start with one Compose command. The earlier deployment
merges two Compose files and expects external model servers. GCP demonstrations also need Gemini
without placing cloud tokens in the operator UI or bypassing grounded-answer validation.

## Decision

Add a standalone Compose file covering Next.js, one API worker, Qdrant, Ollama, a model initializer,
and the existing HTTP reranker. Retain process/container boundaries on one machine. Use private
service DNS and named persistent volumes; publish only the loopback frontend. Select this file
with `COMPOSE_FILE` in a private `.env`, allowing plain `docker compose up --build -d`.

The initializer explicitly downloads the configured embedding and optional generator models.
Reranker weights load in their own service and persistent cache. Keep the UI available during
downloads; distinguish process health, installed models and an actually usable indexed corpus.
Build the CPU reranker with a separate `cpu-models` extra from the official PyTorch CPU index,
without retaining download caches. Preserve the existing `local-models` extra for other deployments.
Do not give the API a Docker socket or adopt Compose containers into native process management.

Add `VertexAIGenerator` behind the existing `Generator` protocol using native text `generateContent`
and a small `google-auth` dependency for ADC discovery and token renewal. Support project/location
selection, global/regional HTTPS origins, and optional server-owned thinking budget. Derive cloud
origins from validated locations and enforce the existing operator origin allowlist. No credentials
or arbitrary cloud endpoint paths are accepted through HTTP. Preserve old saved settings with
defaults for the added provider fields.

Only generation changes when selecting Vertex. Continue existing context limits, Pydantic answer
parsing, citation/year validation and abstention. Reject blocked, truncated or malformed provider
responses. Do not retry billable requests or silently switch providers. Readiness checks validate
ADC availability rather than pretending a local `/v1/models` probe works for Vertex.

## Consequences

One VM can host the complete stack, initially on CPU, and can use attached GCP identity without
long-lived service-account keys. The first startup needs network access, disk capacity and time
for large ML dependencies and weights. Saved connections still override YAML connection defaults.
Old bind-mounted data is not automatically migrated into the new named volumes.

Text generation compatibility is implemented; live Vertex quality, IAM/model access and regional
availability still need rehearsal. Thinking controls differ by Gemini model. There is no streaming,
multimodal support, Gemini embedding migration, GPU orchestration, distributed jobs, or public
query authentication in this change. Existing deployment files remain compatible.
