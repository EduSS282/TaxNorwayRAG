# ADR 0006: Orchestrate grounded generation as a fail-closed application service

## Status

Accepted.

## Context

The repository had independently tested retrieval, routing, context, prompt, generation, citation,
and abstention components, but no application boundary composed them. Calling the generator
directly would allow malformed output, unsupported citations, wrong-year evidence, or insufficient
evidence to appear as a normal answer.

## Decision

- `GroundedRagService` is the single orchestration boundary for tax answers.
- Deterministic tax-year resolution and routing run before retrieval or generation.
- Router risk determines the minimum evidence count; the model cannot change it.
- Generated output must parse as `RagAnswer` and pass deterministic citation, source metadata,
  quote-bound, and tax-year validation.
- Invalid grounding becomes a canonical citation-free abstention. Malformed JSON or runtime
  provider failures become an explicit `failed` result.
- Results expose `answered`, `clarification_required`, `abstained`, or `failed`; callers never infer
  application state from answer prose.
- The CLI may render these results as text or JSON, but never returns raw model text.
- Runtime dependencies remain injected protocols so deterministic tests require no model download
  or network service.

## Consequences

The online path is auditable and conservative: availability failures cannot silently become tax
claims, and unsupported model output cannot bypass grounding checks. Operators can distinguish a
clarification or safe abstention from infrastructure failure.

The validator guarantees traceability, not semantic entailment of every claim. Full prompt token
accounting, exact copied-quote comparison, persistent embedding caching, real-corpus quality
thresholds, and an authenticated HTTP API remain separate work.
