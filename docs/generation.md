# Grounded generation: current status and next milestone

## Status

Grounded generation is **partially implemented but not runnable end to end**. The repository has
the core domain objects and adapters, but no application service or CLI command composes them.

| Capability | Status |
| --- | --- |
| Bounded evidence context | Implemented and unit tested |
| Structured `RagAnswer` and citations | Implemented and unit tested |
| Evidence-bound prompt | Implemented and unit tested |
| OpenAI-compatible generation adapter | Implemented and unit tested |
| Citation identity/metadata validation | Implemented and unit tested |
| Canonical abstention object | Implemented and unit tested |
| Generator endpoint configuration/factory | Not implemented |
| Generated JSON parsing and recovery policy | Not implemented |
| Router-to-generator orchestration | Not implemented |
| `taxguide answer` or HTTP answer endpoint | Not implemented |
| Quote-span/source-text validation | Not implemented |
| End-to-end prompt-injection handling | Not implemented |
| Real generation benchmark baseline | Not implemented |

The `generation` section in `configs/base.yaml` selects a profile, model name, temperature, token
limit, and structured-output preference. It does not currently define a provider, base URL,
timeout, authentication, or context budget, and no production code reads it to build a generator.

## Required orchestration

The next service should make every transition explicit and fail closed:

```text
question
  → classify intent/topic/risk
  → resolve tax year or return clarification
  → retrieve with pre-ranking metadata filters
  → optionally rerank
  → verify year and evidence threshold
  → build bounded context
  → construct grounded messages
  → generate structured JSON
  → parse as RagAnswer
  → validate tax year, citations, source metadata, and quote spans
  → return answered or canonical abstained result
```

`GroundedRagService` should depend on protocols/factories rather than instantiate Qdrant, model
clients, or policy classes internally. Tests must be able to inject deterministic retrievers and
generators without downloading models.

## Proposed application result

The application boundary must distinguish operational state from generated prose. A caller should
not infer abstention by searching the answer text. The service result should contain an explicit
status such as:

- `answered`: a parsed, validated `RagAnswer` with at least one valid citation;
- `clarification_required`: deterministic questions returned before retrieval/generation;
- `abstained`: a canonical low-confidence answer with no unsupported tax claim;
- `failed`: a model, parsing, vector-store, or configuration failure suitable for operator logs.

Model output must never be allowed to choose `failed`, override routing filters, lower the evidence
threshold, or mark its own citations as valid.

## Validation requirements

Before an answer is released, the orchestrator must verify:

1. the output is valid JSON matching `RagAnswer`;
2. non-abstained output contains citations;
3. every citation ID maps to context actually supplied to the model;
4. chunk ID, source URL, and title match that context;
5. a declared quote span is inside the cited chunk and selects the claimed source text;
6. the answer's tax year matches the resolved request year;
7. evidence meets the router's risk-dependent minimum count;
8. empty, conflicting, wrong-year, or invalid evidence produces abstention rather than a best guess.

Retrieved source text is untrusted data. Prompt construction should delimit it as evidence and
instruct the model not to follow commands contained inside it. Deterministic post-generation
validation remains mandatory because prompt instructions alone are not a security boundary.

## Configuration needed by the milestone

The following illustrates the missing configuration contract; it is not accepted by the current
Pydantic model yet:

```yaml
generation:
  provider: openai_compatible
  base_url: http://127.0.0.1:8080
  model: Qwen/Qwen3-4B-Instruct-2507
  timeout: 180.0
  context_max_tokens: 4096
  evidence_max_tokens: 2400
  temperature: 0.1
  max_tokens: 1000
  structured_output: true
```

Provider authentication should remain optional for loopback development and required before a
model endpoint is exposed beyond a trusted private network.

## Definition of done

The grounded-generation milestone is complete only when:

- a clean local setup can create/validate its vector collection and run the documented workflow;
- configuration and factories build every runtime dependency;
- `taxguide answer` exercises the complete path;
- deterministic end-to-end tests cover answer, clarification, abstention, malformed JSON, model
  failure, invalid citation, invalid quote span, insufficient evidence, and cross-year evidence;
- one opt-in live smoke test runs against Qdrant, embeddings, reranker, and generator;
- README, architecture, configuration, CLI examples, and operational documentation are updated in
  the same commit;
- assumptions, deferred work, and benchmark limitations remain explicit.

Persistent embedding caching and production-quality benchmark baselines can follow as separate
milestones, but the orchestrator must expose the measurements and dependency seams they require.
