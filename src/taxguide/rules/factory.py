"""Composition for deterministic query routing."""

from taxguide.domain.taxonomy import ControlledTaxonomy
from taxguide.query.classification import RuleBasedIntentClassifier
from taxguide.query.risk import RuleBasedRiskClassifier
from taxguide.rules.routing import DeterministicTaxRouter


def create_tax_router() -> DeterministicTaxRouter:
    """Create the default deterministic router with one shared taxonomy."""
    taxonomy = ControlledTaxonomy()
    return DeterministicTaxRouter(
        intent_classifier=RuleBasedIntentClassifier(taxonomy=taxonomy),
        risk_classifier=RuleBasedRiskClassifier(),
        taxonomy=taxonomy,
    )
