You are working on TaxGuide Norway.

Create a repository-native retrieval evaluation benchmark with an initial
hand-reviewed question set for TaxGuide Norway.

IMPORTANT:
- Inspect the repository first.
- Read AGENTS.md.
- Inspect all existing evaluation/retrieval code and tests before adding new
  infrastructure.
- Use norway_tax_rag_architecture.md ONLY as design reference.
- Reuse existing retrieval metrics and abstractions wherever possible.
- Do not reimplement Recall, MRR, nDCG, retrieval, RRF, or reranking if they
  already exist.
- Work ONLY on retrieval evaluation.
- Do not implement generation.

==================================================
GOAL
==================================================

Create an executable evaluation test/benchmark in the repository that compares:

    dense
    sparse
    hybrid
    reranked

using the same queries and gold relevance judgments.

The benchmark must measure at least:

    Recall@1
    Recall@5
    Recall@10
    MRR
    nDCG@5
    nDCG@10
    latency

The initial dataset should contain approximately 30 questions.

==================================================
1. DATASET
==================================================

Create a versioned dataset such as:

    data/evaluation/retrieval_gold_v1.json

or follow the existing evaluation-data convention if the repository already
defines one.

Each record should contain conceptually:

{
  "id": "foreign_bank_account",
  "query": "Where do I report a foreign bank account?",
  "language": "en",
  "relevant": [
    {
      "source_url": "...",
      "relevance": 3
    }
  ],
  "notes": "..."
}

Use graded relevance:

    3 = direct/specific answer
    2 = clearly relevant supporting evidence
    1 = related/general evidence
    0 = irrelevant

Do not require every query to have more than one relevant document.

==================================================
2. INITIAL QUESTIONS
==================================================

Create around 30 natural-language questions covering the currently indexed
personal-tax corpus.

The questions must NOT merely copy page titles.

Use realistic user phrasing and paraphrases.

Cover topics such as:

- foreign bank account
- foreign income and wealth
- foreign digital banks such as Revolut/Monzo
- loans outside Norway
- interest on debt abroad
- foreign currency loans
- childcare deduction
- childcare deduction limits
- sale of home/property
- inherited property sale
- renting out property
- tax value of property
- shares and securities
- foreign shares
- tax return corrections
- pre-filled tax return information
- beginner tax return guidance
- employment income
- pension/disability benefits
- moving abroad
- tax residence
- gifts/inheritance
- investment fraud if relevant to indexed tax corpus
- deductions
- bank/loan information
- income/wealth abroad

IMPORTANT:
Only include a question as a benchmark query when the repository's current
corpus contains known relevant evidence.

Do NOT invent gold URLs.

Determine gold URLs from:
- existing crawl manifests
- parsed/indexed corpus
- known repository fixtures/data

If a topic does not currently have known evidence in the corpus, omit it or
mark it separately as a coverage case rather than counting it as a retrieval
failure.

==================================================
3. INCLUDE KNOWN REGRESSION CASES
==================================================

Include these known queries and gold relevance:

A)

Query:

    Where do I report a foreign bank account?

Direct/gold page:

    https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/abroad/income-and-wealth-abroad/income-and-wealth-abroad/

The passage discussing:
- foreign bank account
- balance on 31 December
- interest income

must have relevance 3.

B)

Query:

    Can I deduct childcare expenses from my taxes?

Direct pages include:

    .../family-and-health/children/child-care-deduction/

with high relevance.

The beginner tax-return page may also be relevant.

C)

Query:

    Do I have to pay tax if I sell my home?

The specific:

    .../property-and-belongings/houses-property-and-plots-of-land/sale2/

must receive higher relevance than generic property hub pages.

D)

Query:

    I have a loan from a bank outside Norway. Where do I report the interest?

The loans-and-interest / interest-on-debt-abroad evidence should be marked
relevant according to actual indexed corpus.

==================================================
4. MULTILINGUAL QUERIES
==================================================

Add a small multilingual subset.

For several concepts, include equivalent queries in:

- English
- Norwegian
- Spanish

For example foreign bank account or childcare deduction.

They may share the same gold source URLs.

Do not make all 30 questions translations; keep most questions conceptually
distinct.

==================================================
5. REPOSITORY-NATIVE EXECUTION
==================================================

Create an evaluation test such as:

    tests/evaluation/test_retrieval_benchmark.py

or follow current repository conventions.

This is a LIVE/integration evaluation because it may require:

- configured embedding backend
- Qdrant
- llama.cpp reranker

Therefore it MUST NOT make ordinary:

    uv run pytest

slow or dependent on external services.

Add an explicit pytest marker, for example:

    retrieval_eval

and register it in project pytest configuration.

The benchmark should run explicitly with something like:

    uv run pytest -m retrieval_eval -s

Prefer also requiring an explicit environment opt-in such as:

    TAXGUIDE_RUN_RETRIEVAL_EVAL=1

so an accidental normal pytest run does not invoke remote services.

Example:

    TAXGUIDE_RUN_RETRIEVAL_EVAL=1 \
    uv run pytest -m retrieval_eval -s

On Windows/Git Bash this should work as:

    TAXGUIDE_RUN_RETRIEVAL_EVAL=1 uv run pytest -m retrieval_eval -s

==================================================
6. PIPELINES
==================================================

Evaluate the existing modes:

    dense
    sparse
    hybrid
    reranked

Reuse existing factories/application composition.

Do NOT duplicate production retrieval logic inside the test.

The benchmark must exercise the real retrieval pipeline as much as practical.

For reranked mode use:

    candidate_limit = 10
    final limit = 5

unless project configuration already provides this value.

This reflects the current development deployment where top-10 candidates are
reranked to top-5.

==================================================
7. RELEVANCE MATCHING
==================================================

Prefer evaluation by stable domain identifiers if they are available.

If the current retrieval result exposes only source URLs reliably, use
normalized source URL matching.

Do not match gold results using arbitrary text substring heuristics.

Normalize harmless URL differences such as trailing slash consistently.

Document the matching rule.

==================================================
8. METRICS
==================================================

Reuse existing metrics under src/taxguide/evaluation if implemented.

Compute per pipeline:

    Recall@1
    Recall@5
    Recall@10
    MRR
    nDCG@5
    nDCG@10

Also measure:

    total latency
    mean query latency
    median query latency
    p95 query latency

If existing metric APIs differ, adapt to them rather than creating duplicate
metric implementations.

==================================================
9. OUTPUT
==================================================

When run with `-s`, print a readable comparison table.

Conceptually:

Pipeline            R@1   R@5   R@10   MRR   nDCG@5   nDCG@10   mean latency
Dense
Sparse
Hybrid
Hybrid+Reranker

Also print failing/weak queries, for example:

    query id
    query
    expected/gold URLs
    retrieved URLs/ranks
    pipeline

This is essential for debugging.

==================================================
10. FAILURE TAXONOMY
==================================================

Support an optional/manual failure label field in the dataset or benchmark
report with these categories:

    DOCUMENT_MISSING
    BAD_PARSE
    BAD_CHUNK
    EMBEDDING_MISS
    SPARSE_MISS
    FUSION_ERROR
    RERANK_ERROR
    BAD_GROUND_TRUTH

Do not automatically guess these labels unless the evidence is deterministic.

They are primarily for manual analysis.

==================================================
11. TEST ASSERTIONS
==================================================

Do NOT initially add aggressive quality thresholds that make CI flaky.

The live evaluation test should at minimum verify:

- dataset loads successfully
- every query has at least one valid gold judgment
- relevance values are valid
- every requested pipeline executes
- result structure is valid
- metrics are finite and within valid ranges
- benchmark report is produced

If adding quality gates, make them conservative and clearly documented.

The purpose of v1 is to establish a baseline.

==================================================
12. OFFLINE TESTS
==================================================

Add normal fast tests that run under regular:

    uv run pytest

for:

- evaluation dataset schema
- duplicate query IDs
- malformed URLs
- invalid relevance grades
- metric aggregation
- URL normalization
- benchmark reporting

These tests must NOT contact Qdrant, Ollama, llama.cpp or the internet.

==================================================
13. OPTIONAL MACHINE-READABLE REPORT
==================================================

Prefer writing an evaluation report to something like:

    data/evaluation/results/retrieval_<timestamp>.json

containing:

- timestamp
- corpus/index configuration
- embedding provider/model
- reranker provider
- candidate limit
- evaluated query IDs
- per-query ranks
- aggregate metrics
- latency

Do not overwrite previous benchmark runs.

If the project already has an evaluation-result format, reuse it.

==================================================
14. DOCUMENTATION
==================================================

Document exactly how to run:

Fast normal tests:

    uv run pytest

Live retrieval benchmark:

    TAXGUIDE_RUN_RETRIEVAL_EVAL=1 \
    uv run pytest -m retrieval_eval -s

Document prerequisites:

- SSH tunnel/services if applicable
- Qdrant collection populated
- configured embedding provider
- configured reranker provider

Use config values rather than hardcoded Oracle IPs.

==================================================
15. NON-GOALS
==================================================

Do NOT:

- modify retrieval algorithms
- tune RRF
- tune embeddings
- change Qdrant
- change reranker models
- add generation metrics
- implement LLM-as-judge
- crawl new pages as part of the benchmark
- download models in tests
- silently treat missing documents as retrieval failures

==================================================
16. VALIDATION
==================================================

Run:

    uv run pytest
    uv run ruff check .
    uv run mypy src

Also validate the live benchmark command structurally using mocks/fakes if real
services are not available during implementation.

Finally report:

- files added
- initial query count
- topic distribution
- multilingual query count
- gold matching rule
- pipelines evaluated
- metrics produced
- exact benchmark command
- normal pytest result
- Ruff result
- mypy result
- known limitations

Do not continue to another issue.