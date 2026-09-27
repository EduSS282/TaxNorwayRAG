You are working on TaxGuide Norway.

Implement configurable embedding backends so the existing corpus indexing and retrieval commands can use an Ollama-hosted embedding model instead of always instantiating the local SentenceTransformer QwenEmbedder.

IMPORTANT:
- Work ONLY on embedding backend selection/configuration.
- Inspect the repository first.
- Read AGENTS.md.
- Use norway_tax_rag_architecture.md only as design reference.
- Do not implement unrelated retrieval, reranking, generation, crawler, corpus, API, or UI features.
- Preserve the existing Embedder Protocol.
- Preserve the existing local QwenEmbedder.
- Do not replace QwenEmbedder with Ollama-specific behavior.

Current problem:

src/taxguide/cli/corpus.py currently does:

    embedder = QwenEmbedder(settings.corpus.embedding_model)

and src/taxguide/cli/retrieve.py also directly depends on QwenEmbedder.

As a result, even when an Ollama server is available, TaxGuide downloads
Qwen/Qwen3-Embedding-0.6B from Hugging Face and executes it locally through
sentence-transformers.

Desired architecture:

                     Embedder Protocol
                    /                \
                   /                  \
          QwenEmbedder             OllamaEmbedder
     sentence-transformers        HTTP /api/embed
              local                    remote

The CLI and application layer must depend only on Embedder, not instantiate a
specific implementation directly.

==================================================
1. IMPLEMENT OLLAMA EMBEDDER
==================================================

Add an Ollama embedding adapter, preferably:

src/taxguide/embeddings/ollama.py

It must implement the existing Embedder Protocol.

Conceptual constructor:

    OllamaEmbedder(
        base_url: str,
        model_id: str,
        timeout: float = ...
    )

Required behavior:

- embed_documents(texts: list[str])
- embed_query(query: str)
- model_id property compatible with the existing Embedder abstraction
- use Ollama's HTTP embedding endpoint:

    POST {base_url}/api/embed

with payload:

    {
        "model": "qwen3-embedding:0.6b",
        "input": [...]
    }

For embed_query, sending one string or a one-element batch is acceptable, but
the implementation should reuse common logic.

Use httpx, preferably the project's existing HTTP dependency.

Do not use the ollama Python SDK unless already used by the project.
A small HTTP adapter is preferred.

Validate:

- HTTP failures
- malformed responses
- missing "embeddings"
- empty result when input was provided
- number of returned vectors matches number of input texts
- all returned vectors have the same dimension
- returned values are numeric

Raise explicit useful errors using the existing exception conventions where
possible.

Do not silently fall back to sentence-transformers if Ollama fails.

==================================================
2. CONFIGURATION
==================================================

Extend the existing corpus configuration cleanly.

Current config includes:

corpus:
  embedding_batch_size: 32
  embedding_model: Qwen/Qwen3-Embedding-0.6B
  qdrant_url: http://localhost:6333
  qdrant_collection: taxguide_chunks

Introduce provider-based configuration.

A reasonable resulting config is:

corpus:
  chunk_strategy: structural
  max_tokens: 512
  overlap_tokens: 0

  embedding_provider: ollama
  embedding_model: qwen3-embedding:0.6b
  embedding_base_url: http://localhost:11434
  embedding_timeout: 120.0
  embedding_batch_size: 32

  qdrant_url: http://localhost:6333
  qdrant_collection: taxguide_chunks_ollama_qwen3_06b

Supported providers initially:

- ollama
- local

"local" should use the existing QwenEmbedder / SentenceTransformer adapter.

Use typed configuration validation.

Prefer an enum or Literal for provider selection.

Do not hardcode localhost or Oracle IP addresses in Python code.

The service URL must come from configuration.

==================================================
3. EMBEDDER FACTORY
==================================================

Add a single composition-root/factory function that creates an Embedder from
settings.

For example conceptually:

    def create_embedder(settings: CorpusSettings) -> Embedder:
        match settings.embedding_provider:
            case "ollama":
                return OllamaEmbedder(...)
            case "local":
                return QwenEmbedder(...)
            case _:
                ...

Place it in an appropriate infrastructure/application composition module after
inspecting project conventions.

Do NOT scatter provider checks through corpus/retrieval code.

==================================================
4. CHANGE CORPUS CLI
==================================================

Modify src/taxguide/cli/corpus.py.

Replace direct construction:

    QwenEmbedder(settings.corpus.embedding_model)

with the shared embedder factory.

The corpus builder itself must continue depending on the Embedder Protocol.

Do not add Ollama-specific logic to CorpusBuilder.

==================================================
5. CHANGE RETRIEVE CLI
==================================================

Modify src/taxguide/cli/retrieve.py.

It must use the exact same configured embedding provider/model as indexing.

Remove the direct QwenEmbedder dependency from the CLI composition layer.

This is critical:

documents and queries MUST be embedded using the same configured embedding
backend/model.

==================================================
6. MODEL IDENTIFICATION
==================================================

Preserve enough information in corpus run metadata to identify not only the
model but also the provider.

For example:

embedding_provider: ollama
embedding_model: qwen3-embedding:0.6b

If the existing corpus run model only stores embedding_model, extend it cleanly
if appropriate.

Do not silently mix indexes produced by different embedding configurations.

==================================================
7. TESTS
==================================================

Tests must not require:

- internet
- Hugging Face
- a real Ollama server
- a real Oracle VM

Mock HTTP responses for Ollama.

Add tests for at least:

1. OllamaEmbedder sends correct endpoint
2. correct model name is sent
3. list[str] is sent as a batch
4. embeddings are returned in input order
5. embed_query works
6. malformed response raises useful error
7. HTTP failure raises useful error
8. wrong number of vectors is rejected
9. inconsistent dimensions are rejected
10. factory selects OllamaEmbedder for provider=ollama
11. factory selects existing QwenEmbedder for provider=local
12. corpus CLI uses factory/configuration
13. retrieval CLI uses same factory/configuration
14. tests do not instantiate SentenceTransformer when provider=ollama

Existing QwenEmbedder tests must continue passing.

==================================================
8. IMPORTANT NON-GOALS
==================================================

Do NOT:

- remove QwenEmbedder
- change chunking
- change Qdrant implementation
- change dense retrieval behavior
- modify reranking
- deploy Ollama
- add SSH logic
- add Oracle-specific logic
- add automatic fallback
- download models
- implement an LLM generator
- modify crawler
- modify parser

The SSH tunnel is infrastructure outside TaxGuide.

TaxGuide should simply see:

http://localhost:11434

when configured that way.

==================================================
9. DOCUMENTATION
==================================================

Document both configurations.

Remote Ollama example:

corpus:
  embedding_provider: ollama
  embedding_model: qwen3-embedding:0.6b
  embedding_base_url: http://localhost:11434

Local SentenceTransformers example:

corpus:
  embedding_provider: local
  embedding_model: Qwen/Qwen3-Embedding-0.6B

Explain explicitly that indexing and retrieval must use the same provider/model
configuration.

==================================================
10. VALIDATION
==================================================

Before finishing run:

uv run pytest
uv run ruff check .
uv run mypy src

Fix failures caused by the implementation.

Finally report:

- files added
- files modified
- config changes
- how provider selection works
- tests added
- pytest result
- Ruff result
- mypy result
- known limitations

Do not continue to another issue.