# Deterministic tax routing

The routing module classifies a query before retrieval in `GroundedRagService`. The implementation
is deliberately rule-based: every output is reproducible and can be inspected without loading a
language model. `taxguide answer` uses it; the lower-level `taxguide retrieve` command continues to
use tax-year resolution and filtering directly.

`ControlledTaxonomy` defines the closed topic vocabulary from architecture section 19 and matches
English, Norwegian, and Spanish aliases. Stored metadata and downstream filters should use
`TaxTopic` values rather than arbitrary strings.

`RuleBasedIntentClassifier` emits the seven original intents plus `uncertain`. Missing vocabulary
is not proof that a question is out of scope. Known unrelated requests (for example, asking for
a poem or a weather forecast) can be `out_of_scope`; an unrecognized or ambiguous request becomes
`uncertain` and asks for clarification without retrieval or generation. A selected year does not
override uncertain scope. An unrelated activity mentioned inside a fiscal question does not by
itself reject that question (for example, asking about deducting a course to bake bread).

For recognized tax questions, priority remains deadline, required documents, reporting,
eligibility, field explanation, then general explanation. Bare `when is` no longer proves a
deadline, and `what does` requires a field/box/casilla marker to become a field explanation.
`matched_terms` records literal normalized matches; a general fallback now records scope matches
instead of claiming that no words were recognized.

`RuleBasedRiskClassifier` maps general explanations to low risk, field/deadline/document/reporting
questions to medium risk, and eligibility, uncertain or out-of-scope requests to high risk. PAYE
opt-out, tax residency, appeals, amount/rate/threshold phrases, and eligibility phrases can override
the primary intent's risk. A mixed deadline/document/reporting question does not become lower-risk
merely because it precedes eligibility in the intent ordering. Eligibility terms are injectable
in the risk classifier, alongside the existing risk mapping and high-risk subjects.

`DeterministicTaxRouter` combines injected classifiers and returns data, not prose:

- `retrieve` selects controlled topic, audience, official-source, and optional year constraints;
- `clarify` is used for uncertain scope, or when a year-sensitive/high-risk query has no year;
- `abstain` is used for unsupported out-of-scope requests.

High-risk routes require at least two evidence chunks. Routing does not infer a tax year, user
residency, eligibility, or any future `TaxProfile` field. A separate tax-year resolver can pass its
explicit result into `route(..., tax_year=...)`. In the current grounded-generation service, only
the resolved tax-year constraint is passed to retrieval. Topic and audience metadata are not yet
enriched consistently on corpus chunks, and official-source eligibility currently comes from the
Skatteetaten-only crawl allowlist rather than a runtime source filter. Do not treat those returned
routing constraints as applied filters until corpus enrichment and retrieval integration are
implemented.

## Supported language normalization and vocabulary

The taxonomy, intent classifier, and risk classifier share Unicode NFKC normalization, case
folding, whitespace normalization, dash variants, and common Spanish acute-accent omissions.
Norwegian `å`, `ø`, and `æ` remain distinct. Matching uses complete words/phrases, not substring
or fuzzy matching: `tax` does not match `taxi` or `syntax`.

Aliases cover curated English/Norwegian/Spanish variants for deductions, allowances, loans,
accounts, income, pensions, dividends, property, crypto and other existing topics. In particular,
`deductible`, `deductibility`, `deducted`, the common `deductable` spelling, `deducible(s)` and
`fradragsberettiget/fradragsberettigede` are recognized. Reporting, documents, eligibility and
deadlines also have expanded phrases. No new tax topic or embedding model is introduced.

Generic `NGO`, `donation`, `home`, `bank`, `family`, `stocks` or `deadline` alone do not establish
a fiscal question. Topic matching remains descriptive; matching an ambiguous topic is not enough
to authorize retrieval. Negation is retained: recognizing “not deductible” classifies a question,
not a conclusion that the expense is or is not deductible.

## Examples

| Query | Outcome without a year | Outcome with 2026 |
| --- | --- | --- |
| Can donations to NGOs deductible? | eligibility; ask year | retrieve; high risk; at least 2 chunks |
| ¿Son deducibles las donaciones a ONGs? | eligibility; ask year | same as above |
| Er gaver fradragsberettiget? | eligibility; ask year | same as above |
| Which NGO should I support? | uncertain; clarify scope | still clarify scope |
| What is the maximum deduction? | ask year | retrieve; high risk |
| What does PAYE mean? | general explanation; retrieve | retrieve with year filter |
| Write a poem about tax. | out of scope; abstain | abstain |

Classification changes do not require rebuilding the corpus. Restart the API to load new rules.
The developer retrieval inspector still runs independently and does not decide routing.

## Verification and limitations

`tests/unit/test_routing_regressions.py` holds a curated multilingual suite covering paraphrases,
plurals, selected spelling variants, negatives, normalization, mixed intents, numeric risk and
unrelated requests. It checks routing with and without a year. Service/HTTP tests verify that
uncertain scope returns `clarification_required` without model calls and that the original NGO
question reaches strict year-filtered retrieval when a year is supplied.

These are deterministic regressions, not a held-out accuracy benchmark or proof of fiscal
correctness. Unknown phrasing still needs clarification. The classifier does not parse arbitrary
grammar, resolve all word senses, support every typo, validate jurisdiction/residency, or decide
deductibility. Definitions containing risk terms can conservatively require a year. Add observed
failures together with positive and negative regression cases; do not relax temporal/citation
validation to make a question pass. See [ADR 0013](adr/0013-uncertain-deterministic-routing.md).
