# ADR 0017: Frontend corpus preparation with saved runtime connections

## Status

Accepted.

## Context

The crawler and runtime settings were available in the frontend, but processing downloaded
captures and uploading vectors required a CLI build. A private Fieldmind demonstration needs
an observable acquisition-to-answer workflow without shell-driven vector uploads. CLI builds
also use YAML, while API operators can save different connection preferences.

## Decision

Expose authenticated `POST /v1/corpus` through the existing fixed-destination Next.js proxy.
Reuse `CorpusBuilder`, deterministic chunker composition, the manifest selector, embedder
factory, Qdrant adapter, index signatures and report repository. Shared composition lives
outside the CLI; the web boundary never invokes shell commands.

The API snapshots saved runtime settings at job start and validates their revision. Preview
performs metadata selection only. Indexing requires explicit confirmation of collection writes.
The browser cannot supply arbitrary endpoints, filesystem paths, executables or credentials.

One worker runs a bounded background preparation job. Its writer lock is shared with acquisition;
the crawler's existing directory lock excludes other web managers. CLI/external writers remain
operator-coordinated. Progress and cancellation occur between documents, so in-flight embedding
or Qdrant requests may delay cancellation. Finished reports persist on the API host; the HTTP
summary omits paths and raw exception messages. Index writes refresh lazy query backends so
new requests rebuild sparse corpus caches, including after partial failures.

## Consequences

Operators can select, parse, chunk, embed, index, inspect progress and download a report without
terminal commands after environment provisioning. The same saved connections serve indexing and
queries. Existing CLI behavior and YAML configuration remain supported.

This is a private, single-worker workflow, not a distributed durable queue or an atomic index
replacement. Cancellation preserves completed writes. Queries already holding a backend snapshot
can retain older sparse caches. Use a dedicated collection for isolated rebuilds. Cloud resource
creation, model installation, formal evaluation, backups and alias promotion remain separate
operations. This decision does not add a Vertex AI adapter or public query authentication.
