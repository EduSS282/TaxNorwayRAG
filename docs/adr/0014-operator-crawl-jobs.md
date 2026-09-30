# ADR 0014: Bounded acquisition jobs behind the operator boundary

Status: accepted, 2026-09-27.

## Context

Operators need to select official sections in the frontend and see existing captures without
running long HTTP requests or confusing downloaded documents with indexed evidence.

## Decision

Add `/crawler` and an authenticated fixed-destination `/api/crawl` → `/v1/crawl` boundary.
Reuse the runtime administrator key/origin policy and the named source catalog shared with CLI.
Keep the crawler orchestration separate from model runtime controls, with injected HTTP clients,
one background thread, a process-local job snapshot, and a writer lock beside the configured
crawl manifests. Accept only catalog IDs, bounded page/depth/year selections and cancellation
by current job ID. Reuse `SkatteetatenCrawler` and atomic artifact storage, adding optional
progress/cancellation hooks without changing CLI defaults.

Inventory verifies stored identities, URL scopes and HTML hashes, and revalidates official year
selectors. Older captures without source IDs remain visible. It does not infer completeness,
freshness or Qdrant coverage. Acquisition writes the API's configured corpus input directories;
indexing and remote file synchronization remain explicit, separate operations.

## Consequences

No task queue, extra service or dependency is required on constrained hardware. One API worker
is mandatory for administration. Browser disconnection does not stop acquisition; cancellation
preserves captures and normal shutdown waits for the worker. A restart loses job progress, not
saved artifacts; durable history/resume are deferred. CLI writers and external synchronization
do not participate in the web writer lock, so operators must keep them mutually exclusive.
Unknown URLs, shell commands and file paths are never accepted through this endpoint.
