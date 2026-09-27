# HTTP API and observability

TaxGuide's FastAPI process is a thin boundary over the existing retrieval, reranking, and
grounded-generation contracts. Install with `uv sync --locked` and start Qdrant plus the model
services required by the selected mode. Administration never downloads models (the optional
in-process sentence-transformers providers may fetch missing weights on first inference). Optional authenticated
administration can start preconfigured services on the API host; see [runtime management](runtime-management.md).

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
| `POST /v1/query` | `question`, optional `mode`, `tax_year`, `retrieval_limit`, `candidate_limit`, `response_language`, `include_context` | Structured `GroundedRagResult` |
| `GET /v1/health` | none | Liveness status only |
| `GET /v1/version` | none | Package and API version |
| `GET /v1/metrics` | none | Per-process aggregate latency seconds by stage |
| `POST /v1/admin` | Operator action and bearer key | Connections, dependency states, owned processes and lifecycle events |

The default mode comes from `retrieval.default_mode` (`dense` in the base config); `sparse`,
`hybrid`, and `reranked` are also accepted. `mode: "all"` is a diagnostic option that runs all
four paths and returns `stages` keyed by `dense`, `sparse`, `fused`, and `reranked`; it may be
expensive and requires the reranker service. Retrieval uses
the same tax-year resolver and post-retrieval year guard as the CLI. `/v1/rerank` accepts complete
TaxGuide `Chunk` objects, including source metadata, so result provenance is preserved. The
interactive OpenAPI schema is available at `/docs` on the bound interface.

`response_language` accepts `en`, `nb`, `es`, or null (existing prompt behavior). It asks the model
to use that language for prose/warnings/missing information without altering citation IDs, URLs,
titles or source excerpts. Compliance is not language-validated. Deterministic clarification and
abstention remain English. `include_context: true` returns the actual bounded evidence under
`final_context.evidence` (each item has `evidence_id`, `chunk`, `score`); otherwise `final_context`
is null. It is also null if routing/retrieval ended before context construction. An empty
constructed context has an empty evidence list. This is opt-in response data, never an access log.

`routing.classification.intent` also accepts `uncertain`: the deterministic router could not
establish a supported tax question from the wording. This returns HTTP 200 with
`status: "clarification_required"` and scope-oriented `clarification_questions`, without retrieval
or generation. A supplied year does not bypass this decision. Clients with exhaustive intent
enums must support this value. `/v1/retrieve` remains an independent diagnostic path, not evidence
that the answer route ran retrieval. See [routing](routing.md).

Example (PowerShell):

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/retrieve" `
  -ContentType "application/json" `
  -Body '{"query":"What is the tax return deadline for 2025?","mode":"hybrid","tax_year":2025,"limit":5}'

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/query" `
  -ContentType "application/json" `
  -Body '{"question":"What is the tax return deadline for 2025?","mode":"hybrid","response_language":"es","include_context":true}'
```

Request validation errors use HTTP 422. Cross-year retriever violations use 502; unavailable
Qdrant/model services and `failed` grounded results use 503. Unexpected errors use a generic 500
response that retains the trace ID. Clarification and abstention are
structured successful outcomes rather than transport failures. `/v1/health` intentionally does
not test external dependencies, so it is not a readiness guarantee.

## Operator administration

Disabled by default (503). Set `TAXGUIDE_ADMIN_TOKEN` to a secret of at least 32 characters and
optionally configure `TAXGUIDE_SERVICE_ORIGINS`, `TAXGUIDE_CONNECTIONS_FILE`, and
`TAXGUIDE_LOCAL_SERVICES` as described in the runtime guide. Run exactly one API worker.
Use `Authorization: Bearer <operator-key>`; invalid keys return 401, direct browser `Origin`
headers return 403. Browser requests must use the same-origin Next.js `/api/admin` proxy.

Actions are `get`, `check`, `save`, `restore`, `start`, `stop`, and `prepare`. `check` accepts
optional draft `connections` without persisting them. `save` takes all connection fields plus
the current `revision`; `restore`, `start`, `stop`, and `prepare` also require that revision.
Process actions use a closed `service` name (`generator`, `embeddings`, `reranker`, `qdrant`);
`stop` requires `confirm_stop: true`. `prepare` accepts the retrieval `mode` and advances through
its dependencies until one is not ready. It does not poll or infer/download missing models.

The response contains `connections`, `revision`, `can_restore`, `allowed_origins`,
`local_services`, `services`, and bounded `events`; draft checks also return `checks`.
`ready` is independent of process ownership. Save conflicts, owned-process configuration changes,
and stale revisions return 409; invalid destinations/inputs return 422; process/runtime failures
return sanitized 503 errors. Responses are not cached. Changing embedding identity requires a
different collection and `confirm_reindex: true`; indexing itself is a separate CLI operation.

## Logging, metrics, and tracing

Each HTTP request emits one JSON log record with method, path, status, duration, request ID, trace
ID, and timed stage spans. Questions, responses, query strings, and source excerpts are not logged.
Unknown URL paths are logged as `<other>` to avoid recording user text placed in a path.
Responses include `X-Request-ID`, `X-Trace-ID`, and W3C `traceparent`; a valid incoming version-00
`traceparent` continues its trace ID. `/v1/metrics` reports count, cumulative/max latency, and
fixed-bucket counts for HTTP requests and the retrieval, reranking, and generation stages. Metrics
are in memory, per process, and reset on restart. Trace spans are logged, not retained in a
searchable backend or propagated to Qdrant/model HTTP calls. OpenTelemetry export is deferred.

Only `/v1/admin` has operator authentication. Query/retrieval endpoints have no authentication,
rate limiting, CORS policy for browser clients, or TLS termination.
Do not expose it directly to the public Internet; use loopback, a private tunnel, or an
authenticated gateway. Run one worker on constrained local hardware unless measured otherwise:
each worker has its own cached adapters and metrics. The [frontend](frontend.md) uses a server-side
proxy, so browser CORS is not needed. Optional local supervision does not provide remote execution
or make public exposure safe.
