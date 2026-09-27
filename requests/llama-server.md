You are working on TaxGuide Norway.

Add llama.cpp / llama-server as a supported remote reranker provider.

IMPORTANT:
- Inspect the repository before changing anything.
- Read AGENTS.md.
- Use norway_tax_rag_architecture.md ONLY as design reference.
- Do NOT treat the architecture document as a request to implement other features.
- Work ONLY on the reranker provider/backend integration described here.
- Preserve all existing reranking providers and behavior.
- Do not modify dense/sparse/hybrid retrieval algorithms.
- Do not modify embeddings, Qdrant, chunking, ingestion, crawler, generation,
  citations, API, or UI.

==================================================
CURRENT STATE
==================================================

TaxGuide already has:

    Reranker Protocol
        |
        +-- QwenReranker
        |     local sentence-transformers / CrossEncoder
        |
        +-- HttpReranker
              custom TaxGuide HTTP reranker service

There is already a reranker factory similar to:

    create_reranker(settings)

and configuration currently supports at least:

    reranker_provider: local
    reranker_provider: http

The retrieval pipeline already supports:

    --mode reranked

and conceptually does:

    hybrid retrieval
        -> candidate_limit candidates
        -> configured reranker
        -> final limit

Do NOT redesign this pipeline.

We now have a llama.cpp `llama-server` running remotely.

From TaxGuide's perspective it is reachable through an SSH tunnel at:

    http://localhost:8001

The server is started separately on the remote VM with a reranking model and
supports the llama.cpp reranking endpoint:

    POST /v1/rerank

SSH/tunnel/server lifecycle is infrastructure outside TaxGuide.

==================================================
GOAL
==================================================

Add a new reranker provider:

    llamacpp

so configuration can be:

    retrieval:
      reranker_provider: llamacpp
      reranker_base_url: http://localhost:8001
      reranker_timeout: 300

and the existing command:

    uv run taxguide retrieve \
      "Do I have to pay tax if I sell my home?" \
      --mode reranked \
      --candidate-limit 20 \
      --limit 5 \
      --collection taxguide_chunks_ollama_qwen3_06b

uses:

    TaxGuide
        -> hybrid candidates
        -> POST http://localhost:8001/v1/rerank
        -> llama-server on remote VM
        -> final reranked results

It must NOT load QwenReranker or sentence-transformers locally when
reranker_provider=llamacpp.

==================================================
1. INSPECT EXISTING CODE
==================================================

Before implementation inspect at least:

    src/taxguide/reranking/base.py
    src/taxguide/reranking/qwen.py
    src/taxguide/reranking/http.py
    src/taxguide/reranking/factory.py
    src/taxguide/retrieval/factory.py
    src/taxguide/config/models.py
    configs/base.yaml

Also inspect all reranking/retrieval tests.

Reuse the existing Reranker protocol and ScoredChunk model.

Do not create a parallel ranking abstraction.

==================================================
2. ADD LLAMACPP RERANKER
==================================================

Add an adapter, preferably:

    src/taxguide/reranking/llamacpp.py

with a class such as:

    LlamaCppReranker

It must implement the existing Reranker protocol.

Conceptual constructor:

    LlamaCppReranker(
        base_url: str,
        timeout: float = 300.0,
    )

Use the project's existing HTTP library, preferably httpx.

Do not add a llama.cpp Python SDK dependency.

==================================================
3. HTTP REQUEST
==================================================

Call:

    POST {base_url}/v1/rerank

For example:

    POST http://localhost:8001/v1/rerank

Send the query and ALL candidate document texts.

Conceptually:

    {
      "query": "Do I have to pay tax if I sell my home?",
      "documents": [
        "...candidate 0...",
        "...candidate 1...",
        "...candidate 2..."
      ],
      "top_n": 3
    }

When called by TaxGuide, use:

    top_n = len(candidates)

because TaxGuide needs the complete reranked candidate set and will apply its
existing final `limit` afterwards.

Do NOT send only the final output limit to llama.cpp unless the existing
retrieval architecture explicitly requires that.

==================================================
4. LLAMA.CPP RESPONSE
==================================================

Do NOT reuse the custom HttpReranker's response contract.

The existing custom HttpReranker expects something like:

    {
      "scores": [...]
    }

llama.cpp has a DIFFERENT API contract.

Parse the actual llama.cpp `/v1/rerank` response format.

Expected conceptual structure is ranked results containing the original
document index and a relevance score, for example:

    {
      "results": [
        {
          "index": 2,
          "relevance_score": 0.91
        },
        {
          "index": 0,
          "relevance_score": 0.73
        },
        {
          "index": 1,
          "relevance_score": 0.12
        }
      ]
    }

Inspect/confirm the current llama.cpp response contract and adapt to it rather
than assuming the custom TaxGuide HTTP schema.

==================================================
5. RESULT MAPPING
==================================================

This is important.

The llama.cpp response may be returned in RANKED order.

Therefore:

- do NOT assume response position == original candidate position
- use the returned `index`
- map each result back to the original candidate
- preserve the score returned by llama.cpp
- return ScoredChunk objects in reranked order

Example:

Candidates:

    0 -> chunk A
    1 -> chunk B
    2 -> chunk C

Response:

    index=2 score=.9
    index=0 score=.7
    index=1 score=.1

TaxGuide result must become:

    chunk C
    chunk A
    chunk B

==================================================
6. VALIDATION
==================================================

Validate the response carefully.

Reject useful errors for:

- HTTP non-success status
- timeout
- connection failure
- malformed JSON
- missing results
- non-list results
- missing index
- invalid index type
- index outside candidate range
- duplicate indices
- missing relevance score
- non-numeric score
- NaN
- +infinity
- -infinity
- unexpected number of results when requesting all candidates

Do not silently drop invalid results.

Do not silently fall back to local reranking.

==================================================
7. SCORES
==================================================

Preserve llama.cpp's relevance score as returned.

Do NOT:

- clamp scores
- apply sigmoid
- apply softmax
- normalize scores
- convert them to probabilities

TaxGuide's generic ScoredChunk should preserve finite ranking scores.

Higher score must represent better ranking.

==================================================
8. CONFIGURATION
==================================================

Extend the typed reranker provider configuration to support:

    local
    http
    llamacpp

Example:

    retrieval:
      reranker_provider: llamacpp
      reranker_model: Qwen/Qwen3-Reranker-0.6B
      reranker_base_url: http://localhost:8001
      reranker_timeout: 300
      candidate_limit: 20

For llama.cpp, the model is already loaded by llama-server, so TaxGuide should
not attempt to download/load the model itself.

Keep `reranker_model` if it is part of the shared configuration model, but do
not instantiate a local model for the llamacpp provider.

Do not hardcode:

- Oracle IP
- localhost:8001 in Python
- SSH configuration

All URLs must come from config.

==================================================
9. FACTORY
==================================================

Extend the existing reranker factory.

Conceptually:

    local
        -> QwenReranker

    http
        -> existing HttpReranker

    llamacpp
        -> LlamaCppReranker

Very important:

When provider=llamacpp:

- do NOT instantiate QwenReranker
- do NOT import/load CrossEncoder unnecessarily
- do NOT access Hugging Face
- do NOT load sentence-transformers model weights

Provider construction should remain lazy enough that only the configured
backend is initialized.

==================================================
10. EXISTING CLI
==================================================

Do NOT add a new retrieval mode.

The existing:

    --mode reranked

must continue to be the public interface.

The configured reranker provider determines the implementation.

Example:

    reranker_provider: local
        --mode reranked
        -> local CrossEncoder

    reranker_provider: http
        --mode reranked
        -> existing custom HTTP service

    reranker_provider: llamacpp
        --mode reranked
        -> llama-server /v1/rerank

==================================================
11. HTTP CLIENT LIFECYCLE
==================================================

Follow existing project patterns.

Avoid creating unnecessary global HTTP clients.

Use explicit timeouts.

The timeout must come from:

    retrieval.reranker_timeout

This remote CPU reranker may initially need a relatively large timeout, such
as 300 seconds.

==================================================
12. TESTS
==================================================

Tests must NOT require:

- a real llama-server
- Oracle VM
- SSH
- internet
- Hugging Face
- sentence-transformers model downloads

Mock the HTTP transport.

Add tests covering at least:

1. provider=llamacpp creates LlamaCppReranker
2. correct endpoint is used:
       /v1/rerank
3. base_url is respected
4. query is sent correctly
5. all candidate texts are sent
6. top_n equals number of candidates
7. returned index maps to correct original chunk
8. ranked response changes chunk order correctly
9. relevance_score is preserved
10. negative finite score is accepted if returned
11. invalid index is rejected
12. out-of-range index is rejected
13. duplicate index is rejected
14. missing index is rejected
15. missing relevance_score is rejected
16. NaN is rejected
17. infinity is rejected
18. malformed JSON is rejected
19. HTTP 4xx/5xx produces useful error
20. timeout produces useful error
21. connection failure produces useful error
22. provider=llamacpp does NOT instantiate QwenReranker
23. provider=llamacpp does NOT load sentence-transformers
24. local provider continues to work
25. existing http provider continues to work
26. existing reranked retrieval pipeline works with a fake LlamaCppReranker

Do not require a real external service in tests.

==================================================
13. DOCUMENTATION
==================================================

Document configuration:

    retrieval:
      reranker_provider: llamacpp
      reranker_base_url: http://localhost:8001
      reranker_timeout: 300

Document expected infrastructure:

    laptop TaxGuide
        |
        | localhost:8001
        | SSH tunnel
        v
    remote llama-server
        |
        -> Qwen3 Reranker GGUF

Document that llama-server is expected to already be running with reranking
enabled.

TaxGuide is NOT responsible for:

- starting llama-server
- downloading its model
- SSH tunneling
- process management
- Oracle VM management

Do not include public IP addresses in repository config/docs.

==================================================
14. NON-GOALS
==================================================

Do NOT:

- remove QwenReranker
- remove HttpReranker
- modify QwenReranker scoring
- rewrite HybridRetriever
- rewrite RRF
- modify dense retrieval
- modify sparse retrieval
- modify embeddings
- modify Qdrant
- modify corpus/indexing
- add Docker
- add Kubernetes
- add SSH code
- implement model downloading
- add generation/LLM features

==================================================
15. MANUAL ACCEPTANCE
==================================================

After implementation I should be able to configure:

    retrieval:
      reranker_provider: llamacpp
      reranker_base_url: http://localhost:8001
      reranker_timeout: 300

and run:

    uv run taxguide retrieve \
      "Do I have to pay tax if I sell my home?" \
      --mode reranked \
      --candidate-limit 20 \
      --limit 5 \
      --collection taxguide_chunks_ollama_qwen3_06b

Expected behavior:

    hybrid retrieval
        -> 20 candidates
        -> POST localhost:8001/v1/rerank
        -> llama-server ranks candidates
        -> TaxGuide maps result indices to chunks
        -> final top 5 displayed

There must be NO:

    Loading weights...
    Hugging Face downloads...
    sentence-transformers model loading...

on the TaxGuide laptop when provider=llamacpp.

==================================================
16. VALIDATION
==================================================

Before finishing run:

    uv run pytest
    uv run ruff check .
    uv run mypy src

Fix regressions caused by this issue.

Finally report:

- files added
- files modified
- exact llama.cpp HTTP request implemented
- exact llama.cpp response format handled
- provider/factory changes
- configuration changes
- validation/error handling
- tests added
- pytest result
- Ruff result
- mypy result
- known limitations

Do not continue to another issue.