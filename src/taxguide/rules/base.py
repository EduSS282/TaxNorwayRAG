"""Stable routing contract independent of retrieval and generation adapters."""

from typing import Protocol

from taxguide.rules.routing import RoutingDecision


class TaxRouter(Protocol):
    def route(self, query: str, *, tax_year: int | None = None) -> RoutingDecision: ...
