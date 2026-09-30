ssh -i "PATH_TO_PRIVATE_KEY" \
  -L 11434:localhost:11434 \
  -L 6333:localhost:6333 \
  -L 8001:localhost:8001 \
  SSH_USER@VM_HOST

ssh -i "PATH_TO_PRIVATE_KEY" \
  -L 11434:localhost:11434 \
  -L 6333:localhost:6333 \
  -L 8001:localhost:8001 \
  SSH_USER@VM_HOST

./build/bin/llama-server \
  -hf ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF:Q8_0 \
  --embedding \
  --rerank \
  --pooling rank \
  --batch-size 2028 \
  --ubatch-size 2028 \
  --host 127.0.0.1 \
  --port 8001
