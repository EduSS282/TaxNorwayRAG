# ADR 0010: Local Next.js frontend and evidence inspection

Status: accepted. Scope: issues #73–#78, User Interface v0.9.

Follow-up: [ADR 0011](0011-operator-connections-and-local-services.md) adds `/settings` and
the fixed admin proxy destination, forwarding authorization exclusively to that endpoint.

## Context

The existing FastAPI boundary already owns grounded answers and diagnostic retrieval. The UI
must expose those contracts without moving fiscal logic into JavaScript, adding browser CORS
requirements, or presenting independent retrieval runs as an answer trace. Real corpus benchmarks
remain pending; the interface is a research preview, not evidence of fiscal quality.

## Decision

- Keep Next.js App Router in `frontend/` with a small client interaction boundary and a Node
  route-handler proxy. Allow only query/retrieve and a fixed server-configured API origin.
- Preserve backend HTTP status and request/trace headers, disable caching, bound payload size
  and upstream wait, and never forward browser cookies/authorization or accept destination URLs.
- Use existing JSON answer/citation contracts. Render untrusted content as text and link only
  HTTP(S) sources. Do not render model HTML or invent citations from retrieval candidates.
- Add optional `response_language` to the query/service contract. It changes generation
  instructions only, preserving evidence and citation validation. Legacy callers omit it.
- Add opt-in `include_context`; return the actual bounded context on the answer result, not
  a reconstructed selection. Default null avoids sending unnecessary excerpts. Keep context
  request-local, with no mutable shared diagnostic state or content logs.
- Show four-stage diagnostic comparisons as independent reruns, with their own trace IDs.
- Bind UI/API to loopback and use private SSH tunnels for the laptop. No public hosting/auth
  is added in this milestone. Oracle remains off the interactive path.

## Consequences

Node becomes an optional runtime alongside Python. Labels support en/nb/es; generator language
compliance is best effort, and deterministic backend text remains English. UI state is ephemeral.
The manual TypeScript types must track the OpenAPI contract; Python integration and browser tests
cover the new fields. Browser tests use a deterministic HTTP double, not a live model benchmark.
The #78 context panel is authentic for the answer, but comparison stages are not atomic snapshots
of a single retrieval execution. Authentication, full prompt token accounting and real benchmark
baselines remain separate work.
