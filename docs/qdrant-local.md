# Local Qdrant

The repository provides a disposable Qdrant instance for development.

Run `docker compose up -d qdrant`, then use the REST API at
`http://localhost:6333` or the dashboard at `http://localhost:6333/dashboard`.
The persistent local files live in `data/qdrant/`, which is ignored by Git.

The Compose service starts Qdrant but does not create an application collection. TaxGuide also does
not create or validate one. Before the first indexed corpus build, create a collection whose vector
dimension matches the configured embedder. The default `qwen3-embedding:0.6b` configuration uses
1024 dimensions and `taxguide_chunks_temporal_v1`:

```powershell
$collectionBody = '{"vectors":{"size":1024,"distance":"Cosine"}}'
Invoke-RestMethod `
  -Method Put `
  -Uri "http://127.0.0.1:6333/collections/taxguide_chunks_temporal_v1" `
  -ContentType "application/json" `
  -Body $collectionBody
```

Use a new collection when the embedding model or dimension changes. Automatic collection
lifecycle management remains part of the next orchestration milestone.

Run `docker compose down` to stop it. Add `-v` only when the local index can be
discarded.

The Compose image is pinned to the Qdrant Python client's 1.19 release line. After
updating an existing local container, run `docker compose up -d --force-recreate`.

The current port mappings publish Qdrant on the host interfaces. They are intended for a trusted
development machine, not an Internet-facing VM. See [local runtime](local-runtime.md) before moving
Qdrant off the workstation.
