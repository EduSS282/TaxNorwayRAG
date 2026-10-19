# One-machine Linux deployment

For the Fieldmind demo, prefer the [published-image deployment](image-deployment.md):
`compose.demo.yaml` runs this same stack using downloaded SHA-tagged images. It needs no source
checkout or builds on the VM. The instructions below retain the source-build option.

`compose.single-host.yaml` is a standalone stack. It needs no additional Compose files.
Frontend, API, Qdrant, Ollama and reranker remain separate containers on one Linux machine.
Compose owns their lifecycle; there is no need to run frontend and backend terminals separately.
The original `compose.yaml` and `compose.production.yaml` remain available for existing deployments.

## First deployment

1. Provision a private Linux VM with Docker Engine and the Docker Compose plugin. Use an x86-64
   VM for the initially supported path. Start with 8 vCPUs, 32 GB RAM and 100 GB disk; these are
   rehearsal estimates, not measured guarantees. The stack runs on CPU without NVIDIA drivers.
2. Check out the repository on that VM. In an editor, copy `.env.single-host.example` to `.env`.
   Set `TAXGUIDE_ADMIN_TOKEN` to a random value of at least 32 characters. Keep the file private.
   `COMPOSE_FILE=compose.single-host.yaml` makes Docker select the complete stack automatically.
3. Run this single deployment command from the repository root:

   ```console
   docker compose up --build -d
   ```

4. Open `http://127.0.0.1:3000` on the host, or use the company VPN/private gateway/tunnel to
   reach its loopback listener. For a different local port, set `TAXGUIDE_UI_PORT` before startup.
5. Unlock `/settings`, check services, then open `/crawler`. Download official sources, preview
   selection, and use **Construir e indexar**. Ask questions and inspect context through `/`.
   There are no manual embedding or Qdrant-upload commands in this workflow.

If you prefer not to set `COMPOSE_FILE`, the equivalent single command is:

```console
docker compose -f compose.single-host.yaml up --build -d
```

The `.env` file is deployment configuration, not a Python config loader. The stack reads
`configs/base.yaml` plus `configs/single-host.yaml`. Saved `/settings` preferences take precedence
for API connections after the first save. Editing YAML does not overwrite those saved preferences.
Do not reuse the old bare `docker compose` local-Qdrant instructions after setting `COMPOSE_FILE`;
use explicit `-f compose.yaml` when intentionally operating the original development stack.

## What starts automatically

| Service | Role | Initial work |
| --- | --- | --- |
| `frontend` | Browser UI and fixed API proxy | Production Next.js build |
| `api` | Operator jobs, retrieval and grounded generation | One Python worker; no model loads at import |
| `qdrant` | Persistent vector index | Empty until frontend indexing |
| `ollama` | Embeddings and optional local generation | One parallel request and one loaded model |
| `models-init` | One-time Ollama bootstrap | Pulls `qwen3-embedding:0.6b` and `qwen3:4b-instruct-2507-q4_K_M` |
| `reranker` | Existing HTTP Qwen reranking service | Downloads/caches its Qwen model and loads it on CPU |

Running `up` authorizes these image, dependency and model downloads. First boot needs outbound
access to container registries, PyPI, the official PyTorch CPU wheel index, Ollama's registry and
Hugging Face. The reranker image installs the locked `cpu-models` extra without a package-download
cache; CUDA libraries are excluded. The separate `local-models` extra remains available for
existing installations. Model caches persist across normal stops and subsequent starts.

The application becomes reachable while model downloads continue, so `/settings` can show missing
models during first boot. API liveness is not inference readiness. `models-init` exiting with code
zero is expected. A failed download is not retried silently by the API; after correcting network
or storage problems, another `docker compose up -d` reruns the initializer. A healthy Qdrant with
no points still needs frontend indexing. Reopening the browser does not itself start downloads.

CPU generation can exceed the application's 180-second timeout. Use smaller questions/context,
measure performance, or choose Vertex AI. This file does not reserve GPUs or install NVIDIA
Container Toolkit. GPU acceleration is a separate host-specific deployment change.

Ollama's supported Docker setup and available model tags are documented in
[Ollama Docker](https://docs.ollama.com/docker) and the
[Qwen3 model catalog](https://ollama.com/library/qwen3/tags).

## Gemini through Vertex AI

Gemini replaces only generation. Collection, chunking, Qwen embeddings, Qdrant, BM25, reranking,
temporal filters and answer/citation validation remain in TaxGuide. No vector migration is needed
when only the generator changes. Retrieved context and the question are sent to Google when
Vertex is selected; obtain Fieldmind's approval for that data flow.

On GCP, enable the Vertex AI API and attach an appropriately scoped service account to the VM.
Grant the required prediction permission, typically through `roles/aiplatform.user`, and use the
`cloud-platform` VM OAuth scope with IAM enforcing access. Confirm model availability, region,
billing and quota with the project administrator. Do not create a long-lived JSON service-account
key just for this deployment. ADC can use the attached identity through the metadata service;
the API container must be able to reach that service. See Google's
[ADC setup](https://docs.cloud.google.com/docs/authentication/provide-credentials-adc) and
[Vertex access control](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/access-control).

In `.env`, set `GOOGLE_CLOUD_PROJECT` if ADC cannot infer the intended project. You may set
`TAXGUIDE_PULL_LOCAL_GENERATOR=false` before first startup to skip the local generator download;
embeddings are still downloaded and served locally. The initial connection defaults to local
generation, so finish selecting Vertex in the browser before asking for a generated answer.

In `/settings`:

1. Select **Gemini · Vertex AI (ADC)** as **Proveedor del LLM**.
2. Enter the Gemini publisher model ID available to the project. `gemini-2.5-flash` is an example,
   not a guarantee that the model is still available in the selected project or region.
3. Enter the GCP project, or leave it empty to use the server's ADC project.
4. Choose `global` or an approved regional location. Global requests use
   `https://aiplatform.googleapis.com`; regional requests use
   `https://LOCATION-aiplatform.googleapis.com`. Add any regional origin to
   `TAXGUIDE_SERVICE_ORIGINS` in `.env` and recreate the API before selecting it.
5. Save and apply. Test connections. The Vertex check obtains ADC credentials; it does not
   generate content or establish model permissions/quota. A real grounded question is still required.
6. Ask a corpus-supported question through `/`, then inspect answer status and citations.

Google credentials never go into the browser, saved connection JSON, prompts, or source control.
The API discovers ADC lazily and refreshes expired access tokens. The existing local generator
still works without any GCP identity. There is no silent fallback from a failed Vertex request
to a local model, and no automatic retry of billable generation.

Outside GCP, provision approved ADC credentials first. If a credential file is required, place
it under the ignored `secrets/` directory and set `GOOGLE_APPLICATION_CREDENTIALS` to its
container path, such as `/run/secrets/google-adc.json`. Only the API receives this read-only mount.
Prefer short-lived/federated ADC over a long-lived key. Host `gcloud` credentials are not
automatically visible inside Docker; the operator must provision the intended ADC configuration.

The adapter uses native `generateContent`, JSON response MIME type and the existing `RagAnswer`
validation. It rejects safety blocks, non-`STOP` finishes, blank results and malformed responses.
It excludes thought text from the returned completion. This is text-only, non-streaming support;
it does not add Gemini embeddings, tools, multimodal input, managed Vertex RAG, or quality parity.
See the [native REST contract](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/projects.locations.publishers.models/generateContent).

`configs/single-host.yaml` sets `vertex_thinking_budget: 0` for compatible Flash models. If the
chosen Gemini model requires thinking or uses a different control, set it to `null` before
startup and adjust `generation.max_tokens` for its output/thinking needs. The default 1000-token
limit can truncate thinking models. These advanced generation budgets remain server-owned YAML
settings. Unsupported budget/model combinations fail safely rather than weakening validation.
`configs/vertex.example.yaml` shows a standalone Vertex generation overlay for other deployments.

## Persistence, lifecycle and recovery

A reachable empty Qdrant reports `needs_setup`, displayed as **Conectado · Falta preparar**.
Build/index through `/crawler` to create the selected collection. Empty Ollama catalogs use the
same state while model bootstrap is pending. If `models-init` or `reranker` containers are absent,
the full stack was not started; start the complete Compose project rather than only its API/UI
services. Internal Qdrant connectivity is checked from the API; it needs no browser-facing port.

Compose creates a separate `taxguide-single-host` project and four named volumes: vectors,
application data (captures, manifests, reports, saved connections), Ollama weights, and reranker
weights. They do not automatically import the older `./data` bind mounts. If an old installation
must be migrated, stop its writers and arrange a reviewed copy/snapshot first.

Only the frontend publishes a host port, bound to loopback. Internal APIs have no public
listeners. Keep the complete application behind private access; queries have no built-in user
authentication. No Docker socket or privileged mode is granted to the API. The app can inspect
these services, but Compose owns their start/stop lifecycle rather than the native-process buttons.

`docker compose stop` stops containers and preserves all volumes. `docker compose up -d` starts
them again. `docker compose down` removes this stack's containers/network but retains volumes;
**do not use `down -v` unless intentionally deleting the corpus, vectors and model caches**.
Back up application artifacts and use consistent Qdrant snapshots before upgrades. The stack is
single-host and single-worker; it does not provide high availability or cloud backup automation.

For deployment diagnosis, `docker compose ps` and `docker compose logs models-init reranker api`
show bootstrap/process failures. These are optional administrator diagnostics, not corpus or vector
upload steps. Do not publish raw provider or model logs containing source context or credentials.

## Verification boundary

Deterministic tests cover Compose wiring, model-name consistency, credential refresh, request
translation, origin restrictions, failure handling, frontend configuration, and retained grounding
validation. They do not download real models or call Vertex. Compose config validation is also
part of CI. A successful image build or deterministic clarification only proves packaging and
application/proxy wiring. It does not establish real model readiness, tax accuracy or GCP access.

## Change record

Deployment files: `compose.single-host.yaml`, `.env.single-host.example`, `Dockerfile.reranker`,
`configs/single-host.yaml`, `configs/vertex.example.yaml`, `.dockerignore`, `.gitignore` and
`.github/workflows/ci.yaml`.

Generation/runtime files: `src/taxguide/generation/vertex.py`, `src/taxguide/generation/factory.py`,
`src/taxguide/config/models.py`, `src/taxguide/runtime/models.py`, `src/taxguide/runtime/controller.py`,
`src/taxguide/runtime/probes.py`, `src/taxguide/runtime/supervisor.py`, `pyproject.toml` and `uv.lock`.
The only added application dependency is `google-auth[requests]` and its locked transitive packages.

Frontend and tests: `frontend/components/runtime-settings.tsx`, `frontend/lib/admin.ts`,
`frontend/tests/administration.spec.ts`, `tests/unit/test_vertex_generator.py`,
`tests/unit/test_single_host_compose.py`, `tests/unit/test_runtime_management.py` and
`tests/unit/test_grounded_rag_service.py`.

Documentation updated together: `README.md`, `docs/architecture.md`, `docs/generation.md`,
`docs/api.md`, `docs/runtime-management.md`, `docs/frontend.md`, `docs/three-machine-deployment.md`,
`docs/production-readiness.md`, `docs/fieldmind-gcp-preparation.md`, this guide and ADR 0018.

On 2026-10-18, `uv run pytest` passed 1035 tests and skipped two opt-in live-model tests. Ruff check,
Ruff format check and `uv run mypy src` passed. Frontend `npm ci`, typecheck, production build,
Chromium installation and all 19 Playwright tests passed. Compose configuration validation passed.
API, frontend and reranker Linux images built successfully. That initial reranker build included
unnecessary CUDA dependencies, subsequently replaced by the CPU extra; a fresh container imported
`CrossEncoder` and the reranker application without downloading
or loading model weights. An isolated Docker smoke verified a deterministic
clarification through the frontend proxy plus Vertex settings save/restore; its test containers
and empty volumes were removed afterward. No real model weights or Vertex calls were used in
these checks. npm reported three pre-existing high-severity findings; frontend dependency
versions were not changed.

### Follow-up: readiness and disk use

The readiness regression checks pass with 1039 Python tests (two opt-in live-model tests skipped),
Ruff, formatting, mypy, frontend typecheck/build and all 20 Playwright tests. A real single-host
frontend proxy returned HTTP 200: embeddings, generation and reranking were available; Qdrant
was reachable with no collection and correctly reported `needs_setup`. These probes do not
evaluate answer quality or populate a corpus. Collection creation/indexing remains a frontend action.

The CPU reranker image measured 1.76 GB in Docker's image listing, versus 18.4 GB for the initial
CUDA-bearing image. A network-disabled container imported CrossEncoder and the application with
`torch.version.cuda is None`. Scoped removal of test image tags and old build-cache records kept
all corpus/model volumes. Docker's reported image total fell from 31.53 to 13.89 GB and build cache
from 23.53 to 6.21 GB. These are Docker accounting figures, not guaranteed Windows free-space gains:
Docker Desktop's virtual disk may retain freed blocks until host-side reclamation/compaction.
Do not delete named volumes to reclaim build space; compaction requires a separate maintenance
window if it stops Docker/WSL.
