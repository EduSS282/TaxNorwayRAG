# Phase 0 + Phase 1 architecture

`RawDocument → ParsedDocument → Document` separates capture, extraction, and cleanup.

- `RawDocument` retains decoded HTML and source identity. Its hash reflects the file
  bytes, including any BOM and line endings, before decoding.
- `ParsedDocument` retains the title, language, and ordered sections. Each section has
  an optional heading and level, typed paragraphs, and links. Their order and levels
  allow parent relationships to be reconstructed using the preceding lower-level heading.
- `Document` adds deterministic normalized text and retains all provenance information.

`Paragraph.kind` distinguishes text, lists, and tables. Lists retain markers,
numbering, and indentation; tables retain rows with separators between cells.
Models reject unknown fields and validate hashes, timezone-aware timestamps,
URLs, and domain/path consistency. Collections are lists; components create new
structures without modifying the input document.

Dependencies point toward contracts and the domain:

```text
CLI → configuration + adapters + pipeline
pipeline → DocumentSource + DocumentParser + DocumentNormalizer
adapters → domain
domain → standard library + Pydantic
```

The pipeline contains no extraction or persistence rules. Configuration loading
recursively merges YAML mappings, replaces scalars, and validates with Pydantic.
Mappings without a schema exist only while reading YAML.

The ID is the SHA-256 hash of the canonical source URL: lowercase scheme/domain,
no default port or fragment, and `/` for an empty path. The path, trailing slash on
nonempty paths, and query are preserved to avoid merging different resources.
The original URL is never replaced with its canonical form.

The content hash identifies a version of the file bytes; it is not a hash of the
normalized text. With an identical file, URL, and clock value, the result is
reproducible. Normal loading records a new timestamp, so the complete JSON changes
between runs.

There are no speculative modules for retrieval, generation, or databases.
