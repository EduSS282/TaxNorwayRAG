# Local runtime and hardware profile

This guide describes the recommended development deployment for the available hardware and the
services required by `taxguide answer`.

For the complete three-machine runbook, including the laptop reranker, Oracle scheduled crawling,
SSH tunnels, configuration overlays, and startup order, see
[three-machine deployment](three-machine-deployment.md).

## Recommended allocation

| Machine | Primary responsibilities | Avoid as a required dependency |
| --- | --- | --- |
| Desktop, GTX 1060 6 GB, 32 GB RAM | TaxGuide, Qdrant, Ollama embeddings, quantized 4B generator | Large context windows or concurrent generation |
| Laptop, i7-13700H, 16 GB RAM | Development, tests, benchmark client, optional CPU reranker | Always-on production service |
| Oracle Free Tier VM, 2 OCPU, 12 GB RAM | Scheduled crawling, backups, reports, optionally secured Qdrant | Interactive embedding, reranking, or generation |

Start with every required runtime service on the desktop. Distributing inference before the local
path is stable adds network and availability failures without improving correctness. The laptop can
host the CPU reranker later if measurement shows worthwhile contention reduction. The VM should
not be in the interactive path until private connectivity, authentication, backups, and monitoring
are in place.

## Runtime processes

The default configuration expects:

| Process | Address | Purpose |
| --- | --- | --- |
| Qdrant | `http://127.0.0.1:6333` | Chunk payload and dense-vector storage |
| Ollama | `http://127.0.0.1:11434` | `qwen3-embedding:0.6b` embeddings |
| llama.cpp reranker | `http://127.0.0.1:8001` | `/v1/rerank` |
| llama.cpp generator | `http://127.0.0.1:8080` | `/v1/chat/completions` grounded generation |

Model services are operator-managed. TaxGuide does not start, stop, update, or supervise them.

## 1. Verify the GPU runtime

On the desktop:

```powershell
nvidia-smi
ollama --version
```

Current Ollama documentation lists the GTX 1060 as supported, subject to its current NVIDIA driver
requirements. Verify those requirements before diagnosing TaxGuide. `ollama ps` shows whether a
loaded model is on GPU, CPU, or split between them.

Keep the generator context at 4096 tokens initially. A quantized 4B generator plus the small
embedding model should fit more reliably than full-precision Transformers, but actual VRAM use must
be measured on the installed llama.cpp/Ollama versions. Do not make 8192 or larger the default
without a repeatable latency and memory measurement.

## 2. Start and initialize Qdrant

```powershell
docker compose up -d qdrant
Invoke-RestMethod -Uri "http://127.0.0.1:6333/healthz"
```

The first `taxguide corpus build --index` probes the configured embedder dimension and creates the
missing `taxguide_chunks_temporal_v1` cosine collection. Later builds validate dimension and
distance before writing. Changing the embedding model or output dimension therefore requires a
new collection name; TaxGuide rejects incompatible reuse.

The provided Compose file publishes ports 6333 and 6334 on the host. Treat it as a development
configuration. Do not run it unchanged on an Internet-facing VM.

## 3. Start embeddings

```powershell
ollama pull qwen3-embedding:0.6b
ollama ps
```

Ollama normally manages its own local server on Windows. Confirm the API before indexing:

```powershell
$embedBody = '{"model":"qwen3-embedding:0.6b","input":["dimension probe"]}'
$embedResponse = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:11434/api/embed" `
  -ContentType "application/json" `
  -Body $embedBody
$embedResponse.embeddings[0].Count
```

The result must match the Qdrant collection dimension.

## 4. Start the reranker when needed

The configured provider is llama.cpp. Run the reranker on CPU first so the generator can reserve
the GTX 1060:

```powershell
llama-server `
  -hf ggml-org/Qwen3-reranker-0.6B-Q8_0-GGUF:Q8_0 `
  --embedding --rerank --pooling rank `
  --host 127.0.0.1 --port 8001 -ngl 0
```

Dense, sparse, and hybrid retrieval do not require this process. Only start it for `reranked` mode.
If CPU reranking interferes with the desktop generator, the same process can run on the laptop and
`retrieval.reranker_base_url` can point to its private LAN/VPN address. Restrict the laptop firewall
to the desktop source address.

## 5. Start the generator

Use a pinned GGUF conversion of `Qwen/Qwen3-4B-Instruct-2507`, initially Q4_K_M and 4096 context:

```powershell
llama-server `
  -m C:\models\qwen3-4b-instruct-2507-q4_k_m.gguf `
  --alias Qwen/Qwen3-4B-Instruct-2507 `
  --host 127.0.0.1 --port 8080 `
  -c 4096 -ngl 99 --jinja
```

Record the exact model repository, revision/hash, quantization, llama.cpp version, context, and
hardware in every benchmark report. A third-party quantization should be pinned and verified rather
than silently tracking a mutable model file.

The base URL, timeout, model identifier, output-token limit, and evidence budget are configured
under `generation` in `configs/base.yaml`. The model identifier sent to the server must match an
identifier accepted by that server.

## 6. Crawl, index, retrieve, and answer

```powershell
uv run taxguide crawl `
  "https://www.skatteetaten.no/en/person/taxes/tax-return/" `
  --max-pages 25 --max-depth 2

uv run taxguide corpus build `
  --url-prefix "/en/person/taxes/" `
  --language en --dry-run

uv run taxguide corpus build `
  --url-prefix "/en/person/taxes/" `
  --language en --index

uv run taxguide retrieve `
  "What is the minimum standard deduction for 2025?" `
  --mode hybrid --limit 5

uv run taxguide answer `
  "What is the minimum standard deduction for 2025?" `
  --mode hybrid
```

Use `--mode reranked` only while the reranker is healthy. There is no automatic fallback when an
external model service is unavailable.

## Oracle VM use

The VM is useful for slow, persistent work:

- scheduled crawling within the configured politeness limits;
- storing crawl/corpus reports and backups;
- running CI-style tests and benchmark coordination;
- hosting Qdrant only after resource measurement and security hardening.

Do not expose Qdrant, Ollama, or llama.cpp directly to the public Internet. Prefer a private VPN or
SSH tunnel, bind services to loopback/private interfaces, enable Qdrant authentication/TLS where
appropriate, and restrict cloud firewall rules. If Qdrant moves to the VM, the current TaxGuide
configuration has no API-key field; use a private tunnel or add explicit secret-aware configuration
before enabling an authenticated remote deployment.

## Operational checks

For a repeatable run, capture:

- Git commit and configuration files;
- corpus manifest/run ID and Qdrant collection name;
- model identifiers, file hashes, quantizations, and runtime versions;
- embedding dimension and document/query instruction policy;
- machine, CPU, RAM, GPU, driver, context length, and concurrency;
- cold and warm latency, throughput, peak RAM/VRAM, and failures.

The existing opt-in retrieval harness reports ranking metrics and latency, but it does not yet
record this complete manifest or provide a committed real-corpus baseline.
