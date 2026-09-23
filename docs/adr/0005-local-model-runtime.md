# ADR 0005: Keep model inference external and use a local-first development topology

## Status

Accepted for development.

## Context

TaxGuide uses an embedding model, a reranker, and a small instruction model. The available hardware
is heterogeneous: a desktop with a 6 GB GTX 1060 and 32 GB RAM, a 16 GB laptop with a strong CPU,
and a 2 OCPU/12 GB Oracle Free Tier VM. Making all three machines mandatory would add network,
security, and availability failure modes before the end-to-end grounded path exists.

The repository already models inference through narrow adapters: Ollama embeddings, local or HTTP
reranking, llama.cpp reranking, and OpenAI-compatible generation. It does not supervise external
processes.

## Decision

- Keep Qdrant, TaxGuide, embeddings, and generation on the desktop for the initial working
  system.
- Run the reranker on CPU first; the laptop is an optional private-network host, not a required
  dependency.
- Reserve the Oracle VM for scheduled crawling, reports, backups, and an optional secured Qdrant
  deployment after measurement.
- Run model servers as separately managed processes behind explicit adapter interfaces.
- Bind development endpoints to loopback. Remote endpoints require private connectivity and
  firewall restrictions; public unauthenticated model/vector endpoints are unsupported.
- Prefer quantized GGUF generation with a 4096-token initial context on the 6 GB GPU and record the
  exact model/runtime/hardware settings in benchmarks.

## Consequences

The initial system has fewer moving parts and can be tested offline with injected fakes. Operators
remain responsible for model downloads, service startup, health checks, upgrades, and secrets.
Moving a component to another machine changes configuration rather than domain or orchestration
code.

The desktop must be running for interactive inference. The VM cannot independently provide useful
interactive generation on the chosen model profile, and high availability is intentionally outside
the current milestone.
