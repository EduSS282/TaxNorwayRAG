# Demo deployment with published Docker images

The demo uses three public Docker Hub repositories under `eduss28`: `taxguide-api`,
`taxguide-frontend`, and `taxguide-reranker`. Publication is configured in the repository's
Quality workflow. On every push to `main`, the Python, frontend and deployment gates must pass
before all three Linux `amd64` images are built and pushed with `sha-<full-commit-SHA>` tags.
Pull requests run checks without publishing. There is no moving `latest` deployment tag.

## One-time publication setup

Create a Docker Hub personal access token with read/write permission for the publisher account.
Store it in the GitHub repository's Actions secret named `DOCKERHUB_TOKEN`; never commit it or
put it in the demo `.env`. The workflow logs in as `eduss28`. Create the three repositories as
public if the account does not automatically create them with the desired visibility.
An interactive Docker Desktop login alone does not authenticate a GitHub-hosted runner.

Push the reviewed changes to `main` and wait for **Quality**, including **publish** and
**demo-bundle**, to finish. Download its `taxguide-demo-sha-<commit>` artifact. The bundle is
created only after all three image publications succeed; do not deploy a partially published tag.
The artifact contains the Compose file, configuration template with the exact tag, this guide
and the full single-host runbook.
Model weights, corpus data, cloud credentials and operator tokens are not included in the bundle
or application images. The API image includes the default YAML configuration and source catalog.

## Installation on the demo VM

Use an x86-64 Linux host with Docker Engine and its Compose plugin. The initial estimate remains
8 vCPUs, 32 GB RAM and 100 GB persistent SSD; measure real workloads before promising latency.
Copy/extract the deployment artifact into a dedicated directory. No source checkout, Python,
Node.js, compiler or image build is needed on the VM.

```console
cp .env.demo.example .env
mkdir -p secrets
```

Edit `.env`: set a random `TAXGUIDE_ADMIN_TOKEN` with at least 32 characters. Preserve the
namespace and exact release tag supplied by the artifact. For GCE/Vertex, enable the API, grant
the attached VM service account the required access and set the project. Set
`TAXGUIDE_PULL_LOCAL_GENERATOR=false` if using only Vertex for generation. Then:

```console
docker compose pull
docker compose up -d --no-build
```

The public repositories need no Docker Hub login to pull, subject to Docker Hub's pull limits.
First startup still downloads Qwen embeddings, optional local generation weights and reranker
weights into persistent volumes. The images do not contain those weights. Bootstrap needs
outbound network access and can take time; the reachable UI does not mean models are ready.

Source catalog corrections are bundled in the API image. Select the corrected release tag before
pulling and recreating containers; pulling an older pinned tag cannot update its catalog. Refresh
the crawler inventory after restarting the API. A custom `/app/configs` mount overrides the bundled
catalog and must be updated separately. Corpus data and index volumes survive image updates.

Only the frontend listens on host loopback at `http://127.0.0.1:3000`. Provide a private tunnel,
VPN or authenticated gateway; query endpoints have no built-in user authentication. Configure
Vertex and check services in `/settings`, acquire/index sources in `/crawler`, then rehearse
real grounded questions. See [the single-host runbook](single-host-deployment.md) for Vertex ADC,
regional origins, model budgets and readiness limitations. External ADC can be mounted from
`secrets/`; on GCE prefer the attached identity. Never put credentials in an image.

The API's configuration is bundled. For advanced host-owned YAML changes, provide all three
bundled files in a local `configs/` directory and add a read-only `/app/configs` bind mount using
a Compose override; otherwise use the supported browser settings. Saved connection preferences
in the data volume take precedence over image YAML defaults.

## Updates and recovery

Stop the previous stack before switching deployments. This demo deliberately retains the
`taxguide-single-host` Compose project name and the same named volumes as the source-build stack.
Do not run both definitions concurrently. Existing configuration bind mounts are not used by
the demo; preserve any required custom settings before switching.

Back up application data and take a consistent Qdrant snapshot before changing versions. Set
`TAXGUIDE_IMAGE_TAG` to another successfully published SHA tag, then repeat `pull` and
`up -d --no-build`. Reverting the tag restores images, not an older corpus or data schema.
`docker compose stop` preserves data. Never use `docker compose down -v` unless intentionally
deleting the corpus, vector index and model caches. Images target CPU Linux `amd64`; GPU
orchestration and ARM builds are outside this deployment.

## Manual publication fallback

After the same checks and `docker login`, a Windows publisher can build and publish the current
working tree with an explicit unique tag:

```powershell
./scripts/publish-images.ps1 -Namespace eduss28 -Tag demo-YYYYMMDD-unique
```

The helper builds all three images before uploading, checks each remote manifest, and writes
VM files under ignored `dist/demo-<tag>/`. It does not run the quality gates or claim the working
tree matches a commit. Prefer the Actions SHA release for the demonstration.

Deterministic checks and packaging smoke tests do not establish live GCP permissions, model
quality, complete corpus coverage or fiscal accuracy. A live end-to-end rehearsal remains required.
