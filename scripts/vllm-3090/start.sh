#!/usr/bin/env bash
# Start abliterated Qwen3.8-27B on 2× RTX 3090 via vLLM (Docker).
set -euo pipefail
cd "$(dirname "$0")"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running."
  exit 1
fi

if ! docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
  echo "NVIDIA Container Toolkit not working. Install nvidia-container-toolkit."
  exit 1
fi

[[ -f .env ]] && set -a && source .env && set +a

echo "Pulling vLLM image and starting server..."
echo "API will be at http://127.0.0.1:${HOST_PORT:-8080}/v1"
echo "Model: twolven/Qwen3.8-27B-abliterated-AWQ-MTP"
echo ""
echo "After boot, verify MTP loaded:"
echo "  docker logs -f qwen38-abliterated-3090 | rg 'Detected MTP|KV cache|SpecDecoding'"
echo ""

docker compose up -d
docker compose logs -f
