# Grounded generation

## Implemented boundary

`taxguide answer` is the end-to-end grounded-generation entry point. It composes deterministic
routing, tax-year resolution, retrieval, optional reranking, bounded evidence selection, an
OpenAI-compatible generator, Pydantic parsing, grounding validation, and safe abstention.

```text
question
  → resolve explicit tax year
  → classify intent/topic/risk
  → clarify or reject out-of-scope requests before model calls
  → retrieve with strict tax-year filtering
  → optionally rerank
  → enforce risk-dependent evidence threshold
  → build bounded context
  → generate a JSON object
  → parse as RagAnswer
  → validate citations, source metadata, quote bounds, and tax year
  → answered | clarification_required | abstained | failed
```

The application never releases raw model text as an answer.

## Configuration

```yaml
generation:
  model_profile: portable
  provider: openai_compatible
  base_url: http://127.0.0.1:8080
  model: Qwen/Qwen3-4B-Instruct-2507
  timeout: 180.0
  evidence_max_tokens: 2400
  max_chunks_per_document: 2
  temperature: 0.1
  max_tokens: 1000
  structured_output: true
```

`structured_output: true` adds the OpenAI-compatible `response_format: {type: json_object}` request.
The prompt also includes the complete `RagAnswer` JSON schema. The response still passes through
Pydantic; server-side JSON mode is not trusted as validation.

The model server is an external process. TaxGuide does not download weights, select a GGUF file,
set the llama.cpp context window, start the process, or supervise it.

## CLI

```powershell
uv run taxguide answer `
  "What is the minimum standard deduction for 2025?" `
  --mode hybrid

uv run taxguide answer `
  "Where do I report foreign income?" `
  --tax-year 2025 `
  --mode reranked `
  --candidate-limit 10 `
  --limit 5 `
  --json
```

The retrieval options match `taxguide retrieve`: `dense`, `sparse`, `hybrid`, and `reranked`, plus
Qdrant URL/collection overrides. Reranked mode requires `candidate-limit >= limit`.

## Result statuses

- `answered`: contains a structured answer with at least one validated citation;
- `clarification_required`: contains deterministic questions and performs no generation;
- `abstained`: contains a canonical low-confidence, citation-free response;
- `failed`: contains a safe operational error and causes the CLI to exit nonzero.

Out-of-scope questions abstain before retrieval. Year-sensitive questions without a year request
clarification. Multiple query years request clarification, while an explicit `--tax-year` that
conflicts with the question is rejected.

High-risk routes require at least two selected evidence chunks; other supported routes require at
least one. The model cannot change these thresholds.

## Validation contract

Before `answered`, the service verifies:

1. the output is valid JSON matching `RagAnswer`;
2. at least one citation is present;
3. every citation ID maps to evidence supplied to the model;
4. chunk ID, source URL, and title exactly match that evidence;
5. cited chunks are not duplicated;
6. quote spans stay inside the chunk and select non-blank source text;
7. the answer year matches the resolved request year when one exists;
8. cited evidence year matches the answer year when the answer declares one.

An invalid citation, year, or quote span produces canonical abstention. Malformed structured output
is an operational failure rather than an attempt to salvage untrusted prose.

Evidence is labelled as untrusted source content in both system and user messages. The model is
instructed never to follow commands embedded in retrieved text. This reduces prompt-injection risk
but is not treated as a security boundary; deterministic output validation remains authoritative.

## Collection lifecycle

`taxguide corpus build --index` now reads the embedder dimension, creates a missing single-vector
cosine collection, and validates an existing collection before upsert. A size mismatch, non-cosine
distance, or named-vector schema fails before writing points.

Retrieval and answer commands do not create an empty collection implicitly. Operators must run an
indexed corpus build before querying.

## Tests

Deterministic tests inject fake retrievers and generators and cover:

- validated answers and propagated tax-year filters;
- missing or ambiguous tax-year clarification;
- out-of-scope and insufficient-evidence abstention;
- high-risk evidence thresholds;
- retrieval/generation failures and malformed JSON;
- invalid citation IDs, chunk identities, source metadata, quote spans, and years;
- CLI text/JSON output and exit codes;
- Qdrant collection creation and incompatible-schema rejection.

The normal suite performs no model downloads or network calls. An opt-in live smoke test exercises
the configured Qdrant, embedding, reranker, and generator services and requires enough indexed
evidence to reach generation:

```powershell
$env:TAXGUIDE_RUN_GENERATION_EVAL = "1"
uv run pytest -m generation_eval -s
```

`TAXGUIDE_GENERATION_EVAL_MODE` selects the retrieval mode (default `reranked`) and
`TAXGUIDE_GENERATION_EVAL_QUESTION` overrides the default 2025 wealth-tax question. The test is a
connectivity/orchestration smoke check, not a quality benchmark.

## Known limitations

- `evidence_max_tokens` counts stored chunk tokens, not rendered metadata, schema, or chat-template
  overhead.
- Quote spans verify location and non-blank text, but `Citation` does not contain a copied quote for
  semantic equality comparison.
- Citation traceability does not prove every generated claim is entailed by its source.
- Router topic/audience decisions are recorded, but the grounded service currently applies only
  the safe populated tax-year filter; corpus enrichment must precede stricter topic/audience
  filtering to avoid false-empty retrieval.
- The embedding cache is process-local, not integrated by the factory, and not persistent.
- No reproducible real-corpus retrieval/generation baseline or release threshold is committed.
- There is no authenticated HTTP API, frontend, model-process supervision, or automatic fallback.
