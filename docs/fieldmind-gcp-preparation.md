# Fieldmind live demonstration: requirements and execution

This checklist answers Pierre's request for the environment needed to host TaxGuide Norway
(TaxNorge), inspect its data pipeline, and discuss its technical choices. It describes a private
technical demonstration, not a production release or a deployment already created in GCP.

Pierre's provisioned private VM now has a dedicated deployment folder and connection runbook:
[`deployments/fieldmind-gcp/`](../deployments/fieldmind-gcp/README.md). It targets the supplied
4 vCPU / 16 GB / 50 GB host, Docker's `/data/docker` data-root, IAP port 8080 and native Vertex
generation in `eu`. These are provided environment details, not proof of deployment or live
model readiness; the earlier resource estimates below describe alternatives.

For the demo, the [published-image path](image-deployment.md) uses `compose.demo.yaml` and
`docker compose pull` followed by `docker compose up -d --no-build`. The deployment artifact
pins all three application images to the same successful `main` commit. Docker Hub publication
requires the Actions registry secret; the VM does not need source code or Python/Node build tools.

The repository now also includes a [standalone Linux stack](single-host-deployment.md) and native
Vertex AI Gemini support. After configuring `.env`, one `docker compose up --build -d` starts
the entire local stack and model bootstrap. Gemini uses server ADC and is selectable in `/settings`.

## List to send to Pierre

1. **A GCP project with billing enabled.** Please provide the project ID, billing owner, approved
   spending limit, and the person responsible for deleting resources after the demonstration.
2. **Scoped access for Eduardo and the Fieldmind reviewers.** A platform administrator should
   provision resources. Eduardo needs access to the selected VM, application deployment, logs,
   and demonstration data. Reviewers need the private application URL and operator credentials
   only if they will run acquisition or indexing. Project Owner access is not required.
3. **An agreed region and network policy.** Prefer a European location approved by Fieldmind.
   Confirm GPU availability and quota before choosing a zone. Provide private application access
   through the company VPN or an authenticated HTTPS gateway. Do not publish the API, Qdrant,
   Ollama, or llama.cpp directly.
4. **Compute and persistent storage.** A Linux Compute Engine VM is the smallest deployment
   change for the existing application. As a starting estimate, reserve 8 vCPUs, 32 GB RAM,
   100 GB persistent SSD, and one NVIDIA L4-class GPU with at least 24 GB VRAM. This is a sizing
   proposal for measurement, not a measured minimum or a guarantee of throughput. CPU-only
   execution is possible but needs a separate latency rehearsal. Retain data when stopping the VM.
5. **Access to an LLM.** The directly supported path is a privately hosted llama.cpp server with
   `Qwen/Qwen3-4B-Instruct-2507`, served under that exact alias, using the GGUF quantization
   described in the local runtime documentation. Prepare and record the model hash, runtime
   revision, license, context size, and GPU settings before the meeting. Alternatively, use the
   standalone stack's Ollama generator or native Vertex AI Gemini with an approved GCP identity,
   enabled Vertex AI API, available model, selected region and sufficient quota.
6. **Embedding and reranking services.** Prepare Ollama with `qwen3-embedding:0.6b`, plus a
   compatible llama.cpp reranker serving `Qwen/Qwen3-Reranker-0.6B`. The generator alone is not
   sufficient for RAG. Dense/hybrid demonstrations need embeddings; four-mode comparison also
   needs the reranker. Start with sequential inference and measure memory use.
7. **Qdrant with a persistent data directory.** The application creates and validates its
   collection, computes embeddings, and writes vectors from the frontend. No manual vector
   upload command is needed. Keep the Qdrant REST endpoint private; the current adapter has no
   Qdrant API-key configuration, so a public authenticated Qdrant Cloud endpoint is not a drop-in
   replacement.
8. **Outbound access and data policy.** Allow HTTPS to official Skatteetaten sources, including
   robots.txt, and approved artifact/model registries during installation. Agree the sections,
   languages, and tax years to demonstrate. No personal tax records or credentials belong in
   queries, the corpus, the repository, or demonstration screenshots.
9. **Application deployment and secrets.** Install the pinned Python and frontend dependencies,
   build the frontend, and configure one API worker. Provide a random operator token of at least
   32 characters through host/deployment secret configuration. Set service origins and the
   frontend's backend URL before startup. Keep secrets on the server; do not use `NEXT_PUBLIC_`.
10. **A rehearsal and evidence package.** Reserve time to acquire a bounded corpus, index it,
    verify model calls, compare retrieval, inspect citations, and test clarification and abstention.
    Record commit, corpus manifests, collection, models, timings, and observed failures. Prepare
    a snapshot/backup, a cleanup date, and a fallback presentation if quota or live services fail.

## Hosting plan and responsibilities

Use a single private Linux host for the first rehearsal: Next.js, FastAPI, Qdrant, Ollama, and
the HTTP reranker. `compose.single-host.yaml` covers the complete set, including model bootstrap.
The earlier merged Compose deployment still supports external llama.cpp/model servers.
This avoids introducing Cloud Run state,
distributed jobs, or a new managed retrieval product before the live demonstration works.

The platform administrator owns initial provisioning: project, billing, IAM, firewall, VM,
driver/runtime installation, model downloads, service startup, persistent mounts, backups, and
the private browser entry point. These operations can be prepared with the GCP Console and an
administrator-owned deployment process. TaxGuide does not create its own GCP host or open tunnels
from the browser. The standalone stack installs container dependencies and downloads configured
models automatically when deployed. Once the host is provisioned,
the demonstration's collection-to-answer workflow runs through the frontend.

For IAM, agree least-privilege grants with the platform administrator rather than assigning a
general owner role. VM administration and deployment permissions belong to the provisioner;
OS Login/IAP access can be scoped to the demonstrator. If secrets or backups use GCP services,
grant the VM service account access only to the required secret versions and backup bucket.
Do not distribute long-lived service-account JSON keys. Enable Compute Engine; enable IAP,
Secret Manager, Cloud Storage, or Artifact Registry only when the selected deployment uses them.
Vertex AI API access is unnecessary for the self-hosted path.

The proposed VM resources and hourly schedule must be priced with Fieldmind's current regional
rates before approval. Include compute/GPU runtime, persistent disks retained while stopped,
snapshots, optional gateway/NAT, and network traffic. Set budget alerts and a shutdown owner.
An alerts-only budget does not cap spending; confirm any spend-cap eligibility separately.
GPU models and capacity vary by zone. See Google's
[GPU locations](https://docs.cloud.google.com/compute/docs/regions-zones/gpu-regions-zones)
and [budget guidance](https://docs.cloud.google.com/billing/docs/how-to/budgets).

## LLM access: local generation or native Vertex AI

Local servers use the existing OpenAI-compatible adapter. Gemini uses a separate native Vertex
`generateContent` adapter behind the same generator interface. It implements server-side ADC
discovery, expired-token refresh, global/regional endpoints, JSON MIME mode and safe provider
failure handling. Existing Pydantic parsing and citation/year checks remain mandatory.

In `/settings`, select `vertex_ai`, an available Gemini model, project and location. Authorize
the Google origin on the host and provide ADC through the VM identity or approved credential
provisioning. Do not paste cloud credentials into the frontend. ADC readiness does not prove
model access or quality. Thinking budgets and model availability need rehearsal; see
[the full Vertex setup](single-host-deployment.md#gemini-through-vertex-ai).

Vertex embeddings remain unimplemented and would require an adapter and compatible collection.
Changing only the generator does not require reindexing. No cloud account, live GPU capacity,
or model access was provisioned by this repository change. Pierre's team must supply those.

## Connection handover before opening the browser

The deployer must provide these values through the existing deployment configuration:

| Item | Required value or decision |
| --- | --- |
| Private application URL | Browser-reachable Next.js, protected by VPN or authenticated gateway |
| `TAXGUIDE_API_URL` | Backend origin reachable from the Next.js server; Compose uses `http://api:8000` |
| `TAXGUIDE_CONFIG` / `TAXGUIDE_OVERLAY` | Server-owned configuration; remove machine-specific defaults |
| `TAXGUIDE_ADMIN_TOKEN` | At least 32 characters; shared privately with the operator |
| `TAXGUIDE_SERVICE_ORIGINS` | Exact trusted HTTP(S) service origins; no paths or embedded credentials |
| `TAXGUIDE_LOCAL_SERVICES` | Optional host-owned profiles for installed local services |
| Corpus inputs | Persistent HTML and crawl manifests in the API's configured directories |
| Preparation reports | Writable, persistent `corpus.report_directory` |
| Runtime preferences | Persistent `TAXGUIDE_CONNECTIONS_FILE`, default `data/runtime/connections.json` |
| Qdrant endpoint | Private API-reachable origin; Compose uses `http://qdrant:6333` |
| Embedding endpoint/model | Ollama origin and installed `qwen3-embedding:0.6b` |
| Generator endpoint/model | llama.cpp origin and exact served alias |
| Reranker endpoint/model | Compatible service origin and exact served alias |

Container loopback means the container itself. Use the deployment's private service DNS or
`host.docker.internal` where supported. Authorize those exact origins before saving them in the
frontend. The base generator address belongs to an earlier private machine and must be replaced.
See [private deployment](production-readiness.md) and [runtime management](runtime-management.md).

## Browser-only preparation and execution

After the deployer hands over the running environment, perform these steps without CLI corpus
builds, vector uploads, or manual Qdrant point creation:

1. Open **Conexiones y servicios** (`/settings`). Unlock with the operator key. Review endpoint
   origins, model names, providers, timeouts, and a dedicated demonstration collection name.
   Test the draft, save it, and check services. Optional local profiles can start already installed
   services on the API host. Remote hosts and container-host processes remain administrator-managed.
2. Open **Corpus / Crawler** (`/crawler`) and unlock. Choose a small set of official sections.
   Start with 10–20 pages per section and explicit annual-rate years where needed. Download,
   inspect counts and unavailable captures, and wait for completion. General guidance can have
   an unknown tax year; annual applicability is not inferred from the download date.
3. In **Preparar corpus e indexar en Qdrant**, click **Actualizar preparación**. Verify the
   displayed saved collection, embedding model, chunk strategy, and token size. Choose a path
   prefix, corpus language, and document limit. **Revisar selección** performs metadata selection
   without loading models or writing points. Filters do not rewrite source years.
4. Optionally click **Construir sin indexar** to exercise parsing and chunking. Review its report.
   This validates processing; it does not create a queryable vector index or save chunk files.
5. Preview again, check **Confirmo escribir vectores**, and click **Construir e indexar**.
   The backend computes vectors and sends them to the saved Qdrant collection. The UI shows
   processed, unchanged, and failed documents; the final report includes generated chunks,
   document-year counts, stage timings, and failure categories. Download the report in the browser.
6. Return to `/settings` and check the collection and services again. A green dependency probe
   is limited readiness evidence. It does not establish model quality or full corpus coverage.
7. Open **Preguntas** (`/`). Choose a question supported by the collected official sources,
   tax year and response language. Start with dense retrieval. Inspect answer status, citations,
   exact source links, and the opt-in final context. Try hybrid, then reranked retrieval.
8. Run **Comparar retrieval** with all services available. Explain dense, BM25, fusion and
   reranking results. These are independent diagnostic runs; the final-context panel belongs
   to the actual answer request. Do not compare raw score scales across different stages.
9. Demonstrate a missing-year clarification and an insufficient-evidence abstention. Review
   failure cases rather than interpreting every completed request as a correct tax answer.
10. Download the preparation summary and record the frozen configuration and observations.
    Lock operator panels when finished. The deployer stops chargeable resources and handles backups.

## Initial RAG configuration and technical discussion

The current base profile uses structural chunks of 512 tokens, no overlap, Ollama Qwen 0.6B
embeddings, cosine vectors in Qdrant, ten reranking candidates and five final retrieval results.
Generation uses up to 2400 evidence tokens, at most two chunks per document, a maximum of 1000
output tokens and temperature 0.1. Provision enough model context for evidence, instructions,
question, and output; verify the actual server limit during rehearsal. Chunking and generation
budgets remain trusted YAML settings; the browser displays chunk settings and edits supported
connections. Query mode, year, language and context inspection are available in the query UI.

Discuss these choices using actual examples:

- **Collection and structure:** official-source allowlists, bounded crawling, robots policy,
  immutable capture hashes, normalized documents and heading-aware chunks.
- **Temporal precision:** verified annual applicability, pre-ranking year filters, unknown-year
  evidence policy, clarification, and no cross-year answer mixing.
- **Retrieval:** semantic matching versus exact terminology, BM25, reciprocal-rank fusion,
  reranking latency, and the difference between retrieved candidates and final answer context.
- **Generation:** evidence IDs, Pydantic output validation, citation/quote validation, conservative
  instruction filtering, and abstention. Valid JSON and valid citations do not prove faithfulness.
- **Operations:** incremental document writes, embedding identity/index signature, saved connection
  snapshots, frontend jobs, persistent artifacts, and the need for reviewed quality measurements.

## Acceptance, assumptions and limitations

The live demonstration passes only when a reviewer can acquire official captures, inspect the
selection, index real embeddings from the frontend, ask a grounded question, inspect citations
and context, and compare retrieval against the same declared model/corpus configuration.
Record observed cold/warm timings; do not invent latency or accuracy targets before rehearsal.

Preparation jobs are single-worker and process-local. Acquisition and preparation exclude each
other. Closing the tab does not cancel a job; reopening and refreshing retrieves its state.
Cancellation waits for the current document and retains existing writes. A build updates its
selected documents; it does not delete all other documents in the collection. Interrupted writes
can leave a partial index. Use a fresh collection when rebuilding with a different embedding model.
The last job summary persists; interrupted work is not automatically resumed.

The browser can select and restore collection connections. Atomic alias promotion/rollback,
Qdrant snapshots, cloud provisioning, model downloads, and the formal evaluation/regression
harness remain deployment or CLI operations; they are not represented as frontend buttons.
The standalone deployment now automates model downloads at stack startup; they are not browser actions.
The browser workflow supports the complete acquisition-to-answer demonstration after provisioning,
not every maintenance task in the repository. Query endpoints have no application authentication;
the private gateway/VPN must protect the whole application, not only the operator pages.

Python and Playwright tests use controlled dependencies. They verify software behavior and do not
establish live GCP reachability, fiscal accuracy, real model throughput, or production readiness.
The reviewed generation study and frozen production corpus baseline remain pending. See
[release evidence](production-readiness.md), [retrieval](retrieval.md), and [generation](generation.md).

## Implementation and verification record

The frontend preparation change includes these application and test files:

- Shared composition: `src/taxguide/chunking/factory.py`, `src/taxguide/corpus/composition.py`,
  `src/taxguide/cli/chunk.py`, `src/taxguide/cli/corpus.py`.
- Preparation lifecycle: `src/taxguide/corpus/management.py`, `src/taxguide/corpus/builder.py`,
  `src/taxguide/crawling/management.py`, `src/taxguide/runtime/controller.py`.
- HTTP boundary: `src/taxguide/api/admin.py`, `src/taxguide/api/app.py`,
  `frontend/app/api/[operation]/route.ts`.
- Browser interface: `frontend/components/corpus-preparation.tsx`,
  `frontend/components/crawler-panel.tsx`, `frontend/lib/corpus.ts`.
- Tests: `tests/unit/test_corpus_management.py`, `tests/unit/test_corpus_cli.py`,
  `frontend/tests/corpus.spec.ts`, `frontend/tests/upstream.mjs`.

Documentation updated in the same change: `README.md`, `docs/architecture.md`, `docs/api.md`,
`docs/corpus.md`, `docs/crawler-ui.md`, `docs/frontend.md`, `docs/runtime-management.md`,
`docs/three-machine-deployment.md`, this checklist, and
`docs/adr/0017-frontend-corpus-preparation.md`.

Verification on 2026-10-18:

- `uv run pytest`: 1003 passed, two opt-in live-model tests skipped.
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`: passed.
- Frontend `npm ci`, `npm run typecheck`, `npm run build`,
  `npx playwright install chromium`, and `npm test`: completed; 18 browser tests passed.
- `git diff --check`: passed before this documentation record was added.

The Python preparation tests exercise actual ingestion and in-memory Qdrant with deterministic
embeddings. Browser tests use controlled upstream responses. Existing dependency installation
reported three high-severity npm audit findings; dependency versions and lockfile were unchanged.
The implementation assumes an already provisioned private host and installed models. No live
GCP or real-model evaluation was performed as part of this change.
