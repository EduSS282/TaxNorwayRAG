# ADR 0020: Dedicated Fieldmind deployment over IAP with EU generation

## Status

Accepted.

## Context and decision

The provisioned GCP VM has no public IP, IAP access on port 8080, a 50 GB disk hosting Docker's
data-root, and a service account authorized for Gemini in `eu`. Keep this environment in the
self-contained `deployments/fieldmind-gcp/` folder with a separate Compose project and volumes.
Publish only frontend `8080:3000`; rely on the platform-owned IAP firewall. Preserve the original
loopback deployment for other hosts. Bootstrap embeddings only, with CPU reranking and native
Vertex generation selected in the mounted overlay from the first API start.

Map the provider's `eu`/`us` locations to `aiplatform.LOCATION.rep.googleapis.com`, retaining
existing global/regional destinations and explicit origin checks. Use ADC from the attached VM
identity without service-account keys or an SDK migration. Omit legacy thinking-budget controls
for the selected Gemini model. Do not fall back to global or another provider.

## Consequences

The deployment files can be transferred without source code or builds. CI emits a separate
Fieldmind artifact after all three images are published. No remote host, IAM, firewall or disk
changes are automated. Initial model downloads, real model access/quality, quota, metadata-service
reachability from containers, resource sizing and the end-to-end demo still require rehearsal.
The IAP frontend listener is appropriate only with the stated private-network/firewall controls.
Existing saved connections override later YAML defaults; local and Fieldmind data are not migrated.
