# ADR 0019: Published images for the single-host demonstration

## Status

Accepted.

## Decision

Keep the existing single-host service boundaries and volumes. Add a pull-only `compose.demo.yaml`
with Linux `amd64` application images from Docker Hub. Bundle the default API configuration and
source catalog in the API image; exclude frontend environment files from the build context.
Models, corpus and credentials remain outside application images.

Publish API, frontend and CPU reranker images after the existing Quality gates succeed on pushes
to `main`. Use full commit SHA tags and emit the deployment artifact only after all image jobs
succeed. Authenticate through the repository's `DOCKERHUB_TOKEN` secret. Retain the source-build
Compose path for development and a manual publisher for recovery.

## Consequences

The demo VM downloads a known version without compiling or cloning the source. Three image pushes
are not an atomic registry transaction; a failed release can leave partial tags and must not be
deployed. SHA tags identify source but registry tags remain mutable; restrict publisher credentials
and do not overwrite release tags. Model download availability, live evaluation, provisioning,
GPU acceleration, backups and private access remain separate operational requirements.
