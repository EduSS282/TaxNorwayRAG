# Local Qdrant

The repository provides a disposable Qdrant instance for development.

Run `docker compose up -d qdrant`, then use the REST API at
`http://localhost:6333` or the dashboard at `http://localhost:6333/dashboard`.
The persistent local files live in `data/qdrant/`, which is ignored by Git.

The Compose service starts Qdrant without an application collection. On
`taxguide corpus build --index`, TaxGuide reads the configured embedder dimension, creates a
missing single-vector cosine collection, and validates an existing collection before upsert.
Incompatible size, distance, or named-vector schemas fail without writing points. Use a new
collection name when the embedding model or dimension changes.

Run `docker compose down` to stop it. Add `-v` only when the local index can be
discarded.

The Compose image is pinned to the Qdrant Python client's 1.19 release line. After
updating an existing local container, run `docker compose up -d --force-recreate`.

The current port mappings publish Qdrant on the host interfaces. They are intended for a trusted
development machine, not an Internet-facing VM. See [local runtime](local-runtime.md) before moving
Qdrant off the workstation.
