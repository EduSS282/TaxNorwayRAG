# ADR 0001 — Modular internal architecture

## Context

The project needs traceable ingestion and components that can be evaluated
independently before adding retrieval and generation.

## Decision

Use a modular internal architecture with explicit domain models instead of
organizing the project around a RAG framework. Use a `src` package layout,
Pydantic v2 for contracts, and Protocol interfaces for dependency injection.

## Alternatives

A single script simplifies the initial setup but mixes responsibilities. A RAG
framework introduces abstractions and dependencies that local ingestion does not need.

## Consequences

Modules can be tested and replaced independently. We must maintain our own
interfaces and orchestration; future modules are added only when needed.
