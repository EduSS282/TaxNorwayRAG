# HTTP API and observability

TaxGuide's FastAPI process is a thin boundary over the existing retrieval, reranking, and
grounded-generation contracts. Install with `uv sync --locked` and start Qdrant plus the model
services required by the selected mode. The API does not download models or start services.

Start from the repository root, bound to loopback:

```console
uv run uvicorn taxguide.api.app:app --host 127.0.0.1 --port 8000
```

`TAXGUIDE_CONFIG` selects the base YAML; `TAXGUIDE_OVERLAY` selects an optional overlay. If neither
is supplied, `configs/base.yaml` is used when present. This mirrors CLI configuration precedence.
For example, on PowerShell:

```powershell
$env:TAXGUIDE_OVERLAY = "configs/desktop.yaml"
uv run uvicorn taxguide.api.app:app --host 127.0.0.1 --port 8000
```

The overlay path above is illustrative; create it for your own deployment. The configured Qdrant
collection may be the `taxguide_current` alias after promotion. Existing model and Qdrant
connection errors are returned as service-unavailable responses, without downstream detail.

## Endpoints

| Endpoint | Input | Output |
| --- | --- | --- |
| `POST /v1/retrieve` | `query`, optional `mode`, `tax_year`, `limit`, `candidate_limit` | Mode and ranked `ScoredChunk` results |
| `POST /v1/rerank` | `query`, full candidate `chunks`, optional `limit` | Reranked `ScoredChunk` results |
| `POST /v1/query` | `question`, optional `mode`, `tax_year`, `retrieval_limit`, `candidate_limit` | Structured `GroundedRagResult` |
| `GET /v1/health` | none | Liveness status only |
| `GET /v1/version` | none | Package and API version |
| `GET /v1/metrics` | none | Per-process aggregate latency seconds by stage |

The default mode comes from `retrieval.default_mode` (`dense` in the base config); `sparse`,
`hybrid`, and `reranked` are also accepted. `mode: "all"` is a diagnostic option that runs all
four paths and returns `stages` keyed by `dense`, `sparse`, `fused`, and `reranked`; it may be
expensive and requires the reranker service. Retrieval uses
the same tax-year resolver and post-retrieval year guard as the CLI. `/v1/rerank` accepts complete
TaxGuide `Chunk` objects, including source metadata, so result provenance is preserved. The
interactive OpenAPI schema is available at `/docs` on the bound interface.

Example (PowerShell):

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/retrieve" `
  -ContentType "application/json" `
  -Body '{"query":"What is the tax return deadline for 2025?","mode":"hybrid","tax_year":2025,"limit":5}'

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/query" `
  -ContentType "application/json" `
  -Body '{"question":"What is the tax return deadline for 2025?","mode":"hybrid"}'
```

Request validation errors use HTTP 422. Cross-year retriever violations use 502; unavailable
Qdrant/model services and `failed` grounded results use 503. Unexpected errors use a generic 500
response that retains the trace ID. Clarification and abstention are
structured successful outcomes rather than transport failures. `/v1/health` intentionally does
not test external dependencies, so it is not a readiness guarantee.

## Logging, metrics, and tracing

Each HTTP request emits one JSON log record with method, path, status, duration, request ID, trace
ID, and timed stage spans. Questions, responses, query strings, and source excerpts are not logged.
Unknown URL paths are logged as `<other>` to avoid recording user text placed in a path.
Responses include `X-Request-ID`, `X-Trace-ID`, and W3C `traceparent`; a valid incoming version-00
`traceparent` continues its trace ID. `/v1/metrics` reports count, cumulative/max latency, and
fixed-bucket counts for HTTP requests and the retrieval, reranking, and generation stages. Metrics
are in memory, per process, and reset on restart. Trace spans are logged, not retained in a
searchable backend or propagated to Qdrant/model HTTP calls. OpenTelemetry export is deferred.

The API has no authentication, rate limiting, CORS policy for browser clients, or TLS termination.
Do not expose it directly to the public Internet; use loopback, a private tunnel, or an
authenticated gateway. Run one worker on constrained local hardware unless measured otherwise:
each worker has its own cached adapters and metrics. There is no frontend or orchestration of
external model processes.
