# RAG threat model (v1 private deployment)

## Scope and assets

The protected assets are tax questions and personal context, operator credentials, local
captures, indexed evidence, model-service endpoints, and the integrity of cited answers.
The supported deployment is private/loopback. This is **not** a public-service security review.

| Boundary | Attacker-controlled input | Current control | Residual risk |
| --- | --- | --- | --- |
| Browser → Next.js proxy → API | Question text, mode, year, request body | Fixed upstream, bounded JSON, origin check on proxy; operator actions require bearer key | Query endpoints lack authentication and rate limiting; private network only |
| Official web → crawler → corpus | Page HTML, redirects, URL parameters | Host/path/robots/size bounds, manifest/hash verification, parser | Official pages or a compromised source can contain malicious instructions or false content |
| Qdrant → prompt | Retrieved chunk text and metadata | Obvious instruction/role markers are omitted, remaining evidence is JSON-encoded and labelled untrusted | Obfuscation and indirect prompt injection may survive; a prompt is not a security boundary |
| Generator → answer | JSON and citations | Pydantic schema, source/chunk/year/quote-span checks, fail-closed abstention | Citation presence does not prove semantic entailment or numerical correctness |
| Operator → services | URLs, profiles, model files | Operator key, origin restriction, URL allowlist, fixed local profiles, one-worker lock | A compromised operator host/key controls services; no remote supervision or secret rotation |
| Logs/metrics | Paths, URLs, errors, user text | API access logs use fixed path labels and numeric/opaque IDs; crawler/local-source logs omit URLs, paths and exception strings | CLI error output and model-service logs are separate; do not ingest personal data |

## Abuse cases to test

1. A retrieved page says “ignore previous instructions” or supplies a forged system/developer
   role. It must not reach the generator; if too little evidence remains, abstain.
2. A page tries to close an evidence delimiter and append new instructions. JSON encoding keeps
   it as data, and the obvious marker is excluded before generation.
3. A model cites a non-supplied chunk, a changed URL, an empty quote span, or a wrong tax year.
   Validation must abstain rather than release the answer.
4. A caller puts personal data into the question, URL path or capture filename. Application
   access/crawler logs must not include it. UI advice discourages entering personal identifiers.
5. A browser tries to mutate `/v1/admin` or `/v1/crawl` directly. Missing key or explicit Origin
   must fail; a leaked key remains a critical incident.

## Operational requirements and open risks

- Bind API, UI, Qdrant and model servers to loopback or private interfaces. Add an authenticated
  gateway, TLS, request limits and an abuse policy **before** any public deployment.
- Treat downloaded HTML and indexed chunks as untrusted. Review corpus diffs, year selectors and
  citation source URLs before promotion. Do not accept arbitrary web crawler seeds in the UI.
- Run Uvicorn with `--no-access-log`; its default access logger is not sanitized by the app.
  Do not put names, identity numbers, tokens or source excerpts in operational logs or benchmark
  artifacts. Model-server and reverse-proxy logging must be configured separately.
- The prompt-injection marker check is deliberately conservative, not an adversarial classifier.
  It can miss paraphrases and exclude benign quotations. Faithfulness is not enforced claim by
  claim; human review of high-stakes answers remains required.
- Unavailable services, malformed JSON and unsafe citations fail closed, but availability and
  answer quality remain unproven until the real-corpus benchmark is run and reviewed.

See [ADR 0015](adr/0015-private-readiness-controls.md) and
[production-readiness checklist](production-readiness.md).
