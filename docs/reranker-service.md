# Remote reranker service

The optional FastAPI service hosts `Qwen/Qwen3-Reranker-0.6B` using
`sentence-transformers` `CrossEncoder`. It loads the model once at application startup and exposes:

- `GET /health`
- `POST /rerank` with `{"query": "...", "documents": ["...", "..."]}`

Run it on the remote machine from the repository checkout:

```bash
uv sync
uv run uvicorn taxguide.reranking.service:app --host 127.0.0.1 --port 8001
```

Bind to `127.0.0.1` when accessing the service through an SSH tunnel. The service returns raw
CrossEncoder scores, including negative logits, as `{"scores": [float, ...]}`. It does not expose
authentication or any production orchestration in this iteration.

Create the SSH tunnel separately, then configure the local TaxGuide process to use its local end:

```yaml
retrieval:
  reranker_provider: http
  reranker_model: Qwen/Qwen3-Reranker-0.6B
  reranker_base_url: http://localhost:8001
  reranker_timeout: 120
  candidate_limit: 10
```

With this configuration, `taxguide retrieve "question" --mode reranked` sends its hybrid candidates
to `POST /rerank`. No fallback to the local model occurs if the HTTP service is unavailable.

## llama.cpp / llama-server

TaxGuide can instead delegate reranking to an already-running `llama-server` configured with a
reranking-capable GGUF model. Configure the local end of the separately managed tunnel:

```yaml
retrieval:
  reranker_provider: llamacpp
  reranker_base_url: http://localhost:8001
  reranker_timeout: 30
  candidate_limit: 10
```

The request path is `POST /v1/rerank`. TaxGuide submits every hybrid candidate with
`top_n` equal to the candidate count, then maps each returned `{index, relevance_score}` back to
the original chunk before applying the requested final CLI limit. Scores are retained unchanged.

```text
TaxGuide laptop → localhost:8001 → SSH tunnel → remote llama-server → reranker GGUF
```

`llama-server` must already be running with reranking enabled. TaxGuide does not start it,
download models, create SSH tunnels, manage its process, or manage remote infrastructure. This
provider does not load `sentence-transformers` or local model weights.

For the configured 0.6B model, a CPU-first development command is:

```powershell
llama-server `
  -hf ggml-org/Qwen3-reranker-0.6B-Q8_0-GGUF:Q8_0 `
  --embedding --rerank --pooling rank `
  --host 127.0.0.1 --port 8001 -ngl 0
```

Dense, sparse, and hybrid modes do not require this service. There is no automatic fallback when
reranked mode cannot reach it.
