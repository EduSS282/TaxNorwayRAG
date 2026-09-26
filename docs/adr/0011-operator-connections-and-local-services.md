# ADR 0011: Operator connections and backend-local service ownership

Status: accepted. Scope: requested app-managed connections and local service controls.

## Decision

Keep lifecycle operations in a dedicated Python runtime module, not the frontend or retrieval
domain. An opt-in bearer-protected admin endpoint accepts a closed set of actions. Next.js proxies
that credential only to the fixed admin endpoint. No token persistence in browser storage,
arbitrary shell commands, executable paths, downloads or remote agents are accepted through HTTP.

Connection origins must be authorized at backend startup. An atomic JSON snapshot stores current
and previous connections with revision-based optimistic concurrency. New settings publish only
after persistence succeeds; new requests capture a coherent config/backend pair, while in-flight
requests retain their previous pair. A process file lock enforces a single controller per state
file. CLI configuration remains independent and does not silently consume web-admin state.

Launch profiles are trusted operator-owned YAML, loaded once. Native child handles and exact
Docker container instance identity define ownership; open ports never do. Already-running
services are external and never stopped. Docker uses an explicit local transport and only starts
an existing stopped, loopback-bound container, without pull/create/delete. Child processes start
hidden on Windows and in separate process groups on POSIX. Normal API shutdown stops owned
services; forced termination may leave orphans that are never automatically readopted.

Local GGUF aliases must match the trusted profile model ID. Embedding model/provider changes
require a new collection name and explicit reindex acknowledgement, not automatic data mutation.
Endpoint changes alone cannot prove model identity or vector compatibility.

Readiness checks are bounded HTTP reads, not inference. Preparation is sequential and stops at
the first unready dependency. One managed GPU llama.cpp profile may run at a time; managed Ollama
is CPU-constrained. This is conservative policy for the user's workstation, not global resource
scheduling or a guarantee of sufficient memory. Raw model output is discarded; only bounded,
content-free lifecycle events are shown.

## Deferred

Remote process control, per-user authorization, provider API keys, automatic downloads/indexing,
distributed supervision, persistent audit history, live resource measurement and automatic
restart/failover are deliberately outside this change. Private deployment remains required.
