# Repository audit — 2026-09-30

## Outcome and scope

GitHub lists **87 issues: 86 closed, one open**. The only open issue is
[#86, Run v1.0 evaluation benchmark](https://github.com/EduSS282/TaxNorwayRAG/issues/86).
The issue inventory was read through the GitHub API; pull requests were excluded. Issue bodies
contain no additional acceptance criteria, so this audit checks titles against the existing
implementation, tests, runbooks, and CI. It is not a proof that every deployment or model is correct.

The starting checkout was clean at `c036db212986fe732d92ede780487aebeefa9313`. Its
[Quality workflow](https://github.com/EduSS282/TaxNorwayRAG/actions/runs/36392826219) completed
successfully, including deterministic Python/browser checks and the Docker deployment smoke.
The local changes described below have separate local verification; they are not covered by that
previous CI run. No issues were closed or changed during this audit.

## Implementation evidence

| Issues | Existing implementation and evidence |
| --- | --- |
| #1–#14 | Project/configuration/domain models, ingestion interfaces, parser/normalizer and CLI; unit fixtures and ingestion integration test; [ingestion](ingestion.md) |
| #15–#22 | Chunk models, tokenizer, fixed/recursive/structural strategies, inspection and benchmark fixtures; chunking unit tests |
| #23–#31 | Embedding interfaces/adapters, standalone batching/cache, Qdrant interface/adapter and dense retrieval CLI; adapter and CLI tests; [local Qdrant](qdrant-local.md) |
| #32–#40 | Preliminary gold set, metrics, BM25, fusion, hybrid, rerankers, filters and comparison harness; retrieval/evaluation tests; [retrieval](retrieval.md) |
| #41–#50 | Bounded context, generator interface/client/profile, schema, prompt, citations, abstention and injected evaluation; generation/service tests; [generation](generation.md) |
| #51–#58 | Temporal metadata/versioning, year resolution, cross-year checks, taxonomy, intent, risk and routing; temporal/routing regressions; [routing](routing.md) |
| #59–#64 | Constrained crawler, source catalog, robots/retry policy, incremental indexing, change detection and aliases; crawler/corpus/index tests; [crawler](crawler.md), [index lifecycle](index-lifecycle.md) |
| #65–#72 | FastAPI endpoints, health/version, structured logs, metrics and tracing; HTTP/backend tests; [API](api.md) |
| #73–#78 | Next.js interface, citations, year/language controls and independent retrieval inspector; browser/proxy tests; [frontend](frontend.md) |
| #79–#82 | PII-minimized logs, conservative retrieved-instruction filtering, threat model and artifact regression gate; deterministic safety/regression tests; [threat model](threat-model.md) |
| #83–#85, #87 | GitHub Actions, private Docker packaging, technical runbooks, demo and diagram; successful committed CI; [readiness](production-readiness.md), [demo](demo.md) |
| #86 | Open: an exploratory real-service retrieval measurement exists; reviewed target-hardware generation and release evaluation remain incomplete |

Closed #26 provides a standalone process-local cache, not persistent factory integration.
Closed #50 provides evaluation contracts and injected evaluators, not a reviewed live quality study.
Closed #84 provides private container deployment, not public production certification.

## Improvements made

- Fix a reproduced cache collision: identical text can have different document/query embeddings,
  but both previously shared a cache key. Keys now include the role. Regression tests cover both
  call orders, duplicate documents, repeated queries, and cache reuse. Old unscoped mapping entries
  are ignored and recomputed; no corpus/index migration is required.
- Add an original, self-contained SVG wordmark, improve README introduction/navigation, add a
  Mermaid architecture map, document an all-local generator overlay, and state pending evaluation
  clearly. No external font/image request is required by the SVG asset.
- Correct architecture claims that no real retrieval result or hardware metadata exists. Link the
  actual exploratory report while preserving its limitations.
- Align architecture, generation, readiness, frontend, and three-machine runbooks with cache
  behavior, Windows npm commands, and deterministic-versus-live evaluation.

## Local verification

Environment: Windows, Python 3.13.0. The project requires Python 3.12+; CI also covers Python 3.12.

| Check | Result |
| --- | --- |
| `uv run pytest` | 994 passed, 2 opt-in live checks skipped; 92% statement coverage |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed; 263 files formatted |
| `uv run mypy src` | Passed; 126 source files |
| `npm ci` | Passed; 33 packages audited, no reported vulnerabilities |
| `npm run typecheck` | Passed |
| `npm run build` | Passed |
| `npx playwright install chromium` | Passed using the existing browser cache with required access |
| `npm test` | 15 Chromium browser/proxy tests passed |
| Private Compose `config --quiet` | Passed |

PowerShell uses `npm.cmd`/`npx.cmd` where script execution policy blocks their `.ps1` wrappers.
Initial uv/npm/browser cache access failures required reruns with permission. A second concurrent
browser run correctly rejected occupied test ports; the original suite completed successfully.
The sandbox could not finish stopping its test servers; after cleaning up those owned servers,
the full browser suite was rerun with permission and passed in 8.2 seconds.
The Python suite reports two third-party deprecation warnings (Starlette/httpx and AnyIO);
neither is a test failure. No dependency change was made solely to suppress them.

## Pending evaluation and known limits

The remaining gate is broader than starting the GPU server:

1. Freeze the corpus, collection, code/configuration and model/runtime/hardware identities.
2. Review the preliminary gold judgments and annual applicability; choose release thresholds.
3. Run all four retrieval modes on the intended deployment and review per-question failures.
4. Run the live GPU grounded-generation smoke and a reviewed quality study covering citations,
   faithfulness, numerical/year accuracy, abstention and adversarial inputs.
5. Save reviewed artifacts, rehearse operational recovery, and obtain a human release decision.

The [2026-09-28 retrieval run](evaluation/v1-retrieval-2026-09-28.md) used real Qdrant/Ollama and a
CPU reranker, but an unfrozen corpus and preliminary judgments. CPU reranking did not improve
Recall@5 over hybrid and exceeded the normal 30-second timeout. Dense remains the configured
default. The aggregate artifact is not a reviewed regression baseline or live generation study.

Persistent cache integration, complete rendered prompt accounting, semantic claim validation,
enriched topic/audience filtering, public authentication/rate limiting, and durable remote
supervision remain documented deferred work. The audit does not introduce future milestones.
Query endpoints stay private/unauthenticated; operator authentication does not protect queries.
No live crawling, index mutation, GPU evaluation, container deployment, or model download was
performed in this audit. Compose validation and previous CI evidence do not test the current
desktop/laptop/Oracle network or external model availability.

Documentation updated in this change: `README.md`, `docs/architecture.md`, `docs/generation.md`,
`docs/production-readiness.md`, `docs/frontend.md`, `docs/three-machine-deployment.md`, this audit,
and `docs/assets/taxguide-logo.svg`. The cache correction preserves the existing architecture;
no new cross-cutting decision or ADR is needed.

All local Markdown links resolve across the 38 files in `README.md` and `docs/`; `git diff --check`
reports no whitespace errors.

## Documentation privacy follow-up

The initial audit left operator-specific endpoint addresses in the runbooks. The follow-up removes
those addresses from `README.md`, `docs/architecture.md`, `docs/local-runtime.md`, and
`docs/three-machine-deployment.md`. `docs/runtime-management.md` now uses reserved `.invalid`
hostnames instead of private-network examples. Archived `requests/connect.md` uses placeholders
for the SSH user, VM host, and private-key path instead of deployment details.

A scan of 51 documentation/artifact files across `README.md`, `docs/`, `Design/`, and `requests/`
finds no non-loopback IPv4 addresses or matches for the checked private-key, access-token, personal
home-directory, or dated SSH-key filename patterns. Standard loopback examples remain because they
describe local service binding rather than identify a machine. This is a pattern scan, not a
guarantee that all possible secrets are absent. Public project/source links remain intentionally.

Operational configuration and test fixtures retain their existing endpoint values; this change
sanitizes documentation without changing deployment behavior. Git history is not rewritten.
The required Python suite passes again (994 passed, two live checks skipped), as do Ruff
check/format and mypy. Frontend code and HTTP contracts do not change, so browser checks are not
repeated for this follow-up.
