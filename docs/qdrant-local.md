# Local Qdrant

Issue #27 provides a disposable local Qdrant instance for development.

Run `docker compose up -d qdrant`, then use the REST API at
`http://localhost:6333` or the dashboard at `http://localhost:6333/dashboard`.
The persistent local files live in `data/qdrant/`, which is ignored by Git.

Run `docker compose down` to stop it. Add `-v` only when the local index can be
discarded.
