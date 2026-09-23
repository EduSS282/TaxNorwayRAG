# Deterministic tax routing

The routing module classifies a query before retrieval in the target grounded service. The
implementation is deliberately rule-based: every output is reproducible and can be inspected
without loading a language model. It is not currently composed by `taxguide retrieve`, which uses
tax-year resolution and filtering directly, and there is no end-to-end `answer` command yet.

`ControlledTaxonomy` defines the closed topic vocabulary from architecture section 19 and matches
English, Norwegian, and Spanish aliases. Stored metadata and downstream filters should use
`TaxTopic` values rather than arbitrary strings.

`RuleBasedIntentClassifier` emits one of the seven intents from section 27. It uses explicit
priority when a query contains more than one signal: deadline, required documents, reporting,
eligibility, field explanation, then general explanation. Queries without a tax-domain signal are
marked out of scope.

`RuleBasedRiskClassifier` maps general explanations to low risk, field/deadline/document/reporting
questions to medium risk, and eligibility or out-of-scope requests to high risk. PAYE opt-out, tax
residency, and appeal terms are always high risk.

`DeterministicTaxRouter` combines injected classifiers and returns data, not prose:

- `retrieve` selects controlled topic, audience, official-source, and optional year filters;
- `clarify` is used when a year-sensitive or high-risk query has no explicit resolved tax year;
- `abstain` is used for unsupported out-of-scope requests.

High-risk routes require at least two evidence chunks. Routing does not infer a tax year, user
residency, eligibility, or any future `TaxProfile` field. A separate tax-year resolver can pass its
explicit result into `route(..., tax_year=...)`.
