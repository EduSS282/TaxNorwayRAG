You are working on the TaxGuide Norway project.

Implement ONLY a batch corpus-building command that selects crawled Skatteetaten documents from crawl manifests and sends the selected documents through the existing TaxGuide ingestion/chunking/indexing pipeline.

IMPORTANT:
- Inspect the repository before making changes.
- Read AGENTS.md.
- Read the relevant parts of norway_tax_rag_architecture.md.
- Do NOT treat norway_tax_rag_architecture.md as a request to implement the entire architecture.
- The current GitHub issue / this prompt defines the implementation scope.
- Reuse existing abstractions and implementations wherever possible.
- Do NOT duplicate parser, normalizer, chunker, embedder, vector store, indexer, crawler, or hashing logic that already exists.

==================================================
CONTEXT
==================================================

The project already has a Skatteetaten crawler.

Crawler artifacts currently follow this structure:

data/raw/skatteetaten/<document_id>.html
data/manifests/crawl/<document_id>.json

The crawl manifest contains provenance and classification metadata such as:

- document_id
- original_url
- final_url
- canonical_url
- retrieved_at
- http_status
- content_type
- content_sha256
- language
- page_type
- wizard metadata
- duplicate_of

The crawler already distinguishes interactive wizard pages from normal static pages.

The project also already contains the downstream RAG components up to retrieval/evaluation.

The missing piece is a clean batch corpus-selection and corpus-processing layer.

==================================================
GOAL
==================================================

Implement a command that can select crawled documents based on their manifest metadata and process the selected documents through the existing pipeline.

The intended user experience should support commands conceptually like:

uv run taxguide corpus build \
  --url-prefix "/en/person/taxes/" \
  --url-prefix "/person/skatt/" \
  --url-prefix "/nn/person/skatt/"

and:

uv run taxguide corpus build \
  --url-prefix "/en/person/taxes/" \
  --language en \
  --exclude-wizards

and eventually:

uv run taxguide corpus build \
  --url-prefix "/en/person/taxes/" \
  --language en \
  --index

The command must NOT filter documents based on filenames.

Selection must be based on crawl manifest metadata.

==================================================
1. CORPUS SELECTION ABSTRACTION
==================================================

Introduce a small explicit corpus-selection layer.

Prefer something conceptually similar to:

class CorpusSelector(Protocol):
    def select(
        self,
        manifests: Iterable[CrawlManifest],
        filters: CorpusFilters,
    ) -> list[CrawlManifest]:
        ...

Adapt naming to the repository conventions.

Create a typed CorpusFilters model.

It should support at least:

- url_prefixes: list[str]
- languages: list[str]
- page_types: list[...]
- exclude_wizards: bool
- include_duplicates: bool
- allowed_http_statuses: list[int]

Use existing enums/models where possible.

Do not create duplicate definitions of crawler page types if they already exist.

==================================================
2. URL PREFIX FILTERING
==================================================

Add repeatable CLI support:

--url-prefix

Example:

uv run taxguide corpus build \
  --url-prefix "/en/person/taxes/" \
  --url-prefix "/person/skatt/" \
  --url-prefix "/nn/person/skatt/"

A document should match if its effective URL path begins with ANY supplied prefix.

Determine the effective URL in this priority order:

1. canonical_url, when valid and on the allowed Skatteetaten host
2. final_url
3. original_url

Use proper URL parsing.

Do NOT implement URL-prefix matching with substring matching over the full JSON text.

Example:

URL:
https://www.skatteetaten.no/en/person/taxes/tax-return/

should match:

/en/person/taxes/

but not:

/person/taxes/

Normalize obvious slash differences.

==================================================
3. LANGUAGE FILTERING
==================================================

Add repeatable:

--language

Examples:

--language en

or:

--language en --language nb

Language matching should use manifest metadata.

Do not infer language using an LLM.

If manifest language is missing:

- exclude it when a language filter is explicitly requested;
- otherwise allow it.

==================================================
4. PAGE TYPE / WIZARD FILTERING
==================================================

Support:

--exclude-wizards

When supplied, exclude manifests where:

page_type == INTERACTIVE_WIZARD

or the equivalent existing enum value.

Also support a generic repeatable page-type filter if it fits the existing architecture cleanly, for example:

--page-type static_article

Do NOT implement wizard traversal.

Do NOT modify crawler behavior.

==================================================
5. DUPLICATE FILTERING
==================================================

By default, exclude documents whose manifest indicates:

duplicate_of != null

because duplicate content should not normally enter the RAG corpus twice.

Provide:

--include-duplicates

to override this behavior.

Do not delete duplicate artifacts.

This command only decides whether they belong to the selected corpus.

==================================================
6. HTTP STATUS AND CONTENT TYPE
==================================================

By default, only select successful HTML documents.

Expected default behavior:

http_status == 200
content_type compatible with text/html

Reject failed/non-HTML artifacts from corpus processing.

Reuse existing manifest fields and content-type helpers if available.

==================================================
7. CORPUS BUILD PIPELINE
==================================================

After selection, pass each selected document into the EXISTING pipeline.

Do not reimplement pipeline internals.

The expected conceptual flow is:

CrawlManifest
    ↓
resolve data/raw/skatteetaten/<document_id>.html
    ↓
existing RawDocument/local source
    ↓
existing parser
    ↓
existing normalizer
    ↓
existing chunker

If --index is supplied:

    ↓
existing embedder
    ↓
existing vector store/indexer

Without --index, corpus build should stop before embeddings/vector indexing.

Use the existing default/recommended chunking strategy from project configuration.

Do not hardcode StructuralChunker if the project already has configurable chunker selection.

==================================================
8. IMPORTANT: DRY RUN
==================================================

Implement:

--dry-run

Example:

uv run taxguide corpus build \
  --url-prefix "/en/person/taxes/" \
  --language en \
  --exclude-wizards \
  --dry-run

This must perform selection only.

It must NOT:

- parse documents;
- generate embeddings;
- write to Qdrant;
- modify existing corpus artifacts.

It should show a useful summary such as:

Corpus selection

Manifests scanned:      8,423
Selected:               1,247
Excluded HTTP status:      12
Excluded non-HTML:          4
Excluded URL prefix:    6,421
Excluded language:        398
Excluded wizard:           91
Excluded duplicates:      250

Languages:
  en: 1,247

Page types:
  static_article: 1,247

This is important because the user must be able to inspect the selected corpus before processing thousands of documents.

==================================================
9. LIST / INSPECTION MODE
==================================================

Add an option:

--list

When supplied, output the selected documents.

Human-readable output should show at least:

document_id
language
page_type
effective URL

Example:

6a3568...  en  static_article  https://www.skatteetaten.no/en/person/taxes/...

Do not print raw HTML.

With:

--json

return machine-readable output.

==================================================
10. BATCH PROCESSING
==================================================

The implementation must be suitable for thousands of documents.

Do NOT load every raw HTML file into memory at once.

Selection may load manifests, but raw document processing should be streaming / one document at a time or in bounded batches.

One bad document must not abort the entire corpus build unless the user explicitly requests fail-fast behavior.

Track:

- selected
- processed
- skipped
- failed
- chunks generated
- indexed documents/chunks when --index is used

At completion, show a summary.

==================================================
11. FAILURE REPORT
==================================================

For documents that fail processing, collect structured errors including:

- document_id
- URL
- pipeline stage
- exception type/category
- concise error message

Persist a run report.

Suggested location:

data/manifests/corpus/<run_id>.json

or use the repository's existing run/report convention.

Do NOT overwrite crawl manifests.

A failed document should remain available for debugging.

==================================================
12. CORPUS RUN MANIFEST
==================================================

Every non-dry-run corpus build should produce a corpus build manifest containing:

- run_id
- started_at
- completed_at
- filters used
- source manifest directory
- number scanned
- number selected
- number processed
- number failed
- number skipped
- chunks generated
- whether indexing was enabled
- embedding configuration identifier/model if indexing
- vector collection name if indexing
- document IDs included
- failures

Use timezone-aware timestamps.

This is important for reproducibility.

==================================================
13. CLI
==================================================

Add commands consistent with the current Typer CLI.

Required conceptual interface:

uv run taxguide corpus build [OPTIONS]

Support at minimum:

--url-prefix TEXT       repeatable
--language TEXT         repeatable
--exclude-wizards
--include-duplicates
--dry-run
--list
--json
--index

If useful and consistent with the project, also support:

--manifest-dir PATH
--raw-dir PATH
--limit INTEGER

A --limit option is especially useful for testing:

uv run taxguide corpus build \
  --url-prefix "/en/person/taxes/" \
  --language en \
  --limit 50 \
  --index

Do not invent unnecessary flags.

==================================================
14. DEFAULT BEHAVIOR
==================================================

The default command:

uv run taxguide corpus build

must NOT blindly index the entire crawl.

Safe default behavior should be:

- select HTTP 200
- select HTML only
- exclude duplicate content
- include static and wizard pages unless explicitly filtered
- process selected pages
- DO NOT index unless --index is explicitly supplied

If processing the entire unfiltered crawl by default is unsafe or inconsistent with existing CLI design, require an explicit selector or --all.

Prefer safety over surprising bulk work.

==================================================
15. INTERACTIVE WIZARD HANDLING
==================================================

Wizard pages require special care.

If wizard pages are included:

- their static HTML content may go through the normal parser;
- preserve page_type metadata;
- preserve wizard metadata;
- do not claim the wizard is complete;
- do not extract hidden branches;
- do not execute JavaScript.

If --exclude-wizards is supplied:

- exclude those pages entirely from this corpus run.

Do not change the crawler or implement wizard traversal in this issue.

==================================================
16. METADATA PROPAGATION
==================================================

Ensure important crawl metadata survives into downstream Document / Chunk metadata where the existing data model supports it.

At minimum preserve provenance for:

- document_id
- source/effective URL
- canonical URL when appropriate
- language
- retrieved_at
- content hash
- page_type

Do not duplicate metadata fields unnecessarily.

Do not silently overwrite downstream tax-year metadata.

==================================================
17. INDEXING MODE
==================================================

When:

--index

is supplied, use the EXISTING embedding + vector indexing components.

Do NOT create a second embedding implementation.

Do NOT create a second Qdrant client abstraction.

Respect project configuration for:

- embedding provider
- embedding model
- embedding batch size
- vector database
- collection name

The current deployment may use an Ollama-compatible remote embedding service through localhost/SSH tunnelling, so all endpoints must remain configuration-driven.

Do not hardcode IP addresses or localhost assumptions.

If embedding or Qdrant are unavailable:

- report the service failure clearly;
- do not corrupt the corpus run;
- preserve the failure report.

==================================================
18. IDEMPOTENCY
==================================================

The operation should be safely repeatable.

Running the same corpus build twice with the same source documents and configuration must not produce arbitrary duplicated corpus records.

Reuse deterministic:

document_id
chunk_id

and existing Qdrant upsert/idempotency behavior.

Do not invent random IDs for documents/chunks.

Run IDs themselves may be unique because they represent executions.

==================================================
19. TESTS
==================================================

Tests must require:

- no internet access;
- no real Ollama service;
- no real Qdrant instance.

Use existing mocks/fakes/test adapters.

Add unit tests covering at least:

1. url-prefix filtering
2. multiple url-prefix filters use OR semantics
3. canonical URL priority
4. fallback to final_url
5. fallback to original_url
6. language filtering
7. multiple language filters
8. missing language behavior
9. wizard exclusion
10. duplicate exclusion by default
11. include-duplicates override
12. HTTP status filtering
13. non-HTML filtering
14. dry-run does not process documents
15. limit behavior
16. effective URL parsing
17. missing raw HTML artifact
18. deterministic selection
19. JSON output structure

Add an integration-style test:

crawl manifests
    ↓
CorpusSelector
    ↓
raw HTML fixture
    ↓
existing parser
    ↓
existing normalizer
    ↓
existing chunker
    ↓
result summary

For indexing-mode integration tests:

use MockEmbedder / fake vector store already present in the repository.

No external services.

==================================================
20. PERFORMANCE
==================================================

This command may process thousands of pages.

Avoid:

- reading all raw HTML files at once;
- storing all embeddings in RAM;
- repeatedly reparsing the same manifest;
- O(n²) duplicate checks.

Prefer bounded batches and streaming where practical.

Keep the implementation simple and explicit.

Do not prematurely introduce distributed processing.

==================================================
21. DOCUMENTATION
==================================================

Add or update documentation for the corpus workflow.

Explain:

Crawler
    ↓
crawl manifests
    ↓
CorpusSelector
    ↓
parser
    ↓
normalizer
    ↓
chunker
    ↓
optional embedding/indexing

Document examples:

A. Inspect English personal-tax corpus:

uv run taxguide corpus build \
  --url-prefix "/en/person/taxes/" \
  --language en \
  --dry-run

B. Inspect Norwegian tax corpus:

uv run taxguide corpus build \
  --url-prefix "/person/skatt/" \
  --language nb \
  --dry-run

C. Inspect all three main tax paths:

uv run taxguide corpus build \
  --url-prefix "/en/person/taxes/" \
  --url-prefix "/person/skatt/" \
  --url-prefix "/nn/person/skatt/" \
  --dry-run

D. Build only 50 English pages for testing:

uv run taxguide corpus build \
  --url-prefix "/en/person/taxes/" \
  --language en \
  --limit 50

E. Build and index them:

uv run taxguide corpus build \
  --url-prefix "/en/person/taxes/" \
  --language en \
  --limit 50 \
  --index

F. Exclude interactive wizard pages:

uv run taxguide corpus build \
  --url-prefix "/en/person/taxes/" \
  --exclude-wizards \
  --index

==================================================
22. NON-GOALS
==================================================

Do NOT implement:

- new crawler
- Scrapy migration
- Zyte integration
- Playwright
- wizard traversal
- new parser
- new chunker
- new embedding model
- new vector database
- LLM generation
- ContextBuilder
- citation generation
- tax-year inference
- scheduler
- incremental crawler
- UI
- FastAPI endpoints
- background jobs

This issue is ONLY:

crawl manifest selection
+
batch corpus processing
+
optional use of existing indexing pipeline

==================================================
23. ENGINEERING REQUIREMENTS
==================================================

Preserve project standards:

- Python 3.12+
- Pydantic v2
- Typer CLI
- pytest
- Ruff
- mypy
- explicit interfaces
- dependency injection
- deterministic IDs
- timezone-aware timestamps
- configuration-driven services
- no LangChain
- no LlamaIndex
- no Haystack
- no unnecessary dependencies

==================================================
24. ACCEPTANCE CRITERIA
==================================================

The implementation is complete when all of these work:

1.

uv run taxguide corpus build \
  --url-prefix "/en/person/taxes/" \
  --dry-run

returns a correct selection summary without processing documents.

2.

uv run taxguide corpus build \
  --url-prefix "/en/person/taxes/" \
  --url-prefix "/person/skatt/" \
  --url-prefix "/nn/person/skatt/" \
  --dry-run

selects documents matching ANY of the prefixes.

3.

--language en

filters using manifest language metadata.

4.

--exclude-wizards

excludes interactive wizard manifests.

5.

Duplicates are excluded by default.

6.

--include-duplicates

allows them.

7.

Only valid successful HTML crawl artifacts are processed by default.

8.

The command resolves HTML files using document_id and the crawler artifact layout, not filenames derived from URLs.

9.

The selected HTML files go through the existing parser, normalizer and chunker.

10.

--index uses the existing embedder/vector indexing implementation.

11.

--dry-run never invokes embeddings or Qdrant.

12.

One malformed document does not destroy the whole batch.

13.

A reproducible corpus run manifest/report is produced.

14.

No external HTTP requests occur in tests.

15.

uv run pytest passes.

16.

uv run ruff check . passes.

17.

uv run mypy src passes.

==================================================
WORKFLOW
==================================================

Before changing code:

1. inspect repository structure;
2. inspect crawler manifest models;
3. inspect crawler artifact repository;
4. inspect current ingestion pipeline;
5. inspect parser and normalizer entry points;
6. inspect chunking API;
7. inspect embedding/indexing APIs;
8. inspect CLI structure;
9. inspect config system;
10. inspect AGENTS.md;
11. inspect relevant architecture documentation.

Then provide a short implementation plan.

Implement only this issue.

After implementation run:

uv run pytest
uv run ruff check .
uv run mypy src

Fix issues caused by the implementation.

Finally report:

- files added
- files modified
- CLI commands/options added
- architecture decisions
- tests added
- pytest result
- Ruff result
- mypy result
- assumptions
- known limitations

Do not continue to another issue.