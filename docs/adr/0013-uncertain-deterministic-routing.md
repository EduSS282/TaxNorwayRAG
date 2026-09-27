# ADR 0013: Separate uncertain wording from unsupported tax scope

Status: accepted, 2026-09-27.

## Context

The literal classifier rejected “Can donations to NGOs deductible?” before retrieval because
`deductible` was absent from its vocabulary. Unknown words were treated as affirmative evidence
of unsupported scope. Conversely, generic topic words such as `home` could admit unrelated tasks.
Intent priority also risked masking an eligibility signal behind reporting or deadline wording.

## Decision

Keep deterministic classification and existing injected interfaces. Expand curated multilingual
aliases and share literal Unicode-aware normalization across taxonomy, intent and risk matching.
Add `QueryIntent.UNCERTAIN`, mapped to `clarify`, with a scope question before year clarification.
No retrieval/generation occurs for uncertain scope, even if a year was selected. Reserve
`out_of_scope` for recognized unrelated requests rather than all vocabulary misses. Generic
ambiguous topic aliases alone are insufficient scope evidence.

Keep primary intent priority but classify eligibility and quantitative risk independently so
mixed questions cannot silently lower evidence requirements. No LLM classifier, fuzzy matching,
dependency, corpus migration or retrieval fallback is added.

## Contract and consequences

The HTTP routing intent enum gains `uncertain`; the existing `clarification_required` result and
`clarification_questions` carry the response. Clients with exhaustive intent enums must accept
the new value. The current frontend displays routing as data and already renders clarification.
Custom complete intent/risk mappings must include `uncertain`.

Some ambiguous or out-of-domain wording now asks for clarification instead of abstaining. The
rules remain incomplete and conservative; they are neither a semantic safety boundary nor a
jurisdiction/eligibility determination. Curated regressions measure consistency, not model
faithfulness or production accuracy. Strict year and citation validation remain unchanged.
