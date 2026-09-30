You are working on TaxGuide Norway.

Fix whitespace loss in parsed/normalized Skatteetaten content.

IMPORTANT:
- Inspect the repository first.
- Read AGENTS.md.
- Use norway_tax_rag_architecture.md ONLY as design reference.
- Work ONLY on whitespace/text-normalization correctness.
- Do not modify retrieval, embeddings, Qdrant, reranking, crawler, generation,
  API, or UI.
- Preserve existing document/chunk IDs unless the project's deterministic ID
  contract intentionally changes when normalized text changes.

==================================================
CURRENT PROBLEM
==================================================

Real indexed chunks contain text such as:

    "foreign institutionsthat are"
    "Calculatethe deduction"
    "must also beable to present"
    "onlyduring the school holidays"
    "from thesale"
    "inyour tax return"
    "thecountry"

The semantic content is correct, but whitespace is being lost around some HTML
element boundaries during parsing and/or normalization.

Examples observed from real Skatteetaten pages include:

    "institutionsare"
    "Calculatethe"
    "beable"
    "onlyduring"
    "forthesale"
    "inyour"
    "thecountry"

This is undesirable because these chunks will later be passed directly to the
LLM generator.

==================================================
GOAL
==================================================

Preserve natural word boundaries when converting Skatteetaten HTML into
TaxGuide text.

Correct:

    "Calculate the deduction"
    "must also be able to present"
    "only during the school holidays"

Incorrect:

    "Calculatethe deduction"
    "must also beable to present"
    "onlyduring the school holidays"

==================================================
1. FIND ROOT CAUSE
==================================================

Inspect:

- SkatteetatenHtmlParser
- HTML text extraction helpers
- normalization pipeline
- list handling
- inline element handling
- block element handling
- link handling
- section/paragraph reconstruction

Determine exactly where adjacent DOM text nodes are concatenated without a
separator.

Do NOT simply apply a regex that guesses where English words should be split.

The fix must be structural.

For example, text nodes separated by meaningful HTML boundaries must be joined
with appropriate whitespace before generic whitespace normalization.

==================================================
2. PRESERVE CORRECT TEXT SEMANTICS
==================================================

The implementation must preserve:

- punctuation
- dates
- percentages
- NOK amounts
- parentheses
- slash-separated terms
- hyphenated words
- links
- headings
- lists
- inline formatting such as strong/em/span/a
- existing intentional punctuation adjacency

Do not introduce spaces such as:

    "31 December ."      incorrect
    "NOK 25 , 000"       incorrect
    "tax - return"       incorrect

The goal is normal prose whitespace, not spacing every DOM node blindly.

==================================================
3. LISTS
==================================================

Ensure list-item extraction does not collapse adjacent items into text such as:

    "- day care - childminder - after-school..."

unless this is intentionally how the current domain model represents lists.

Prefer preserving meaningful separators/newlines according to the existing
Document/Section/Paragraph models.

Do not redesign the domain model in this issue.

==================================================
4. REAL REGRESSION FIXTURES
==================================================

Add realistic HTML fixtures reproducing the exact classes of failures observed
in production.

Include cases equivalent to:

    Calculate <a>the deduction</a>
    must also <strong>be able</strong> to present
    only <span>during</span> the school holidays
    foreign institutions <em>that are</em>
    Norway <a>in your tax return</a>

Use representative Skatteetaten-like markup.

Do not hardcode fixes for specific URLs or text strings.

==================================================
5. TESTS
==================================================

Add regression tests verifying at least:

- adjacent inline elements retain word boundaries
- links retain surrounding spaces
- strong/em/span boundaries retain spaces
- nested inline elements retain spaces
- punctuation remains correct
- no spaces are inserted before punctuation
- list-item text remains readable
- existing parser fixtures still pass
- normalized output is idempotent
- repeated normalization does not continually change whitespace

Where appropriate, add assertions for exact expected text.

==================================================
6. VERIFY REAL CONTENT
==================================================

If existing repository fixtures/raw samples contain the affected structures,
add regression coverage using them.

Do not make tests depend on the internet.

==================================================
7. NON-GOALS
==================================================

Do NOT:

- modify crawler behavior
- change chunk sizes
- change embeddings
- change retrieval
- modify reranker
- modify Qdrant
- add generation
- rewrite the parser wholesale
- use language-specific heuristics to split concatenated words

==================================================
8. VALIDATION
==================================================

Run:

    uv run pytest
    uv run ruff check .
    uv run mypy src

Then run at least one existing parse/corpus fixture through the pipeline and
show that previously broken examples now contain correct whitespace.

Finally report:

- root cause
- files changed
- extraction/normalization behavior changed
- regression tests added
- pytest result
- Ruff result
- mypy result
- known limitations

Do not continue to another issue.