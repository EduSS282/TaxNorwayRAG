# ADR 0009: Thin HTTP boundary and request-scoped observability

## Status

Accepted.

## Context

The grounded CLI already composed retrieval, reranking, and generation services. A new HTTP
boundary should expose these independently without duplicating RAG logic or loading model weights
on import. Operational debugging needs timing and correlation without logging tax questions or
generated answers.

## Decision

- Add an injectable FastAPI application factory and a configured backend that lazily caches
  existing retrieval/reranking/answer adapters per process.
- Keep `/v1/retrieve`, `/v1/rerank`, and `/v1/query` separate. Reuse temporal retrieval checks and
  structured grounded results; map invalid input and service failures to explicit HTTP statuses.
- Add request IDs and W3C trace IDs to responses and JSON access logs. Time retrieval, reranking,
  generation, and total HTTP requests with fixed stage names, aggregating process-local metrics.
- Log no request bodies, query strings, answer content, source excerpts, or unknown URL paths.
  Return generic unavailable/internal messages for failures while retaining trace headers.

## Consequences and limits

The API is suitable for local/private use and can be tested with injected backends without GPU
or Qdrant. Health is liveness, not dependency readiness. Traces and metrics are in-process only;
there is no external collector or downstream span propagation. The API has no authentication,
rate limiting, public TLS termination, frontend, or model-service supervision. Those operational
capabilities must be added before a public deployment.
