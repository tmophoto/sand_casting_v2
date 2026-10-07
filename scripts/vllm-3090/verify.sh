#!/usr/bin/env bash
# Quick health check after vLLM boots.
set -euo pipefail
PORT="${HOST_PORT:-8080}"

echo "=== models ==="
curl -s "http://127.0.0.1:${PORT}/v1/models" | python3 -m json.tool 2>/dev/null || curl -s "http://127.0.0.1:${PORT}/v1/models"

echo ""
echo "=== chat (thinking off) ==="
curl -s "http://127.0.0.1:${PORT}/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen3.8-27b-abliterated",
    "messages": [{"role":"user","content":"Reply with exactly: ok"}],
    "max_tokens": 16,
    "temperature": 0.6,
    "top_p": 0.95,
    "top_k": 20,
    "chat_template_kwargs": {"enable_thinking": false}
  }' | python3 -m json.tool 2>/dev/null | head -40

echo ""
echo "Check container logs for:"
echo "  - Detected MTP model"
echo "  - GPU KV cache size (~560900 tokens)"
echo "  - SpecDecoding acceptance ~2.9/3"
