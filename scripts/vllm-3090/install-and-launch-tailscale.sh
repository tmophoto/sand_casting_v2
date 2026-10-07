#!/usr/bin/env bash
# One-shot: download twolven/Qwen3.8-27B-abliterated-AWQ-MTP, launch vLLM on 2×3090,
# expose on all interfaces for Tailscale access.
#
# Run on YOUR GPU machine (WSL2 Ubuntu recommended on Windows):
#   cd scripts/vllm-3090 && ./install-and-launch-tailscale.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODEL_ID="twolven/Qwen3.8-27B-abliterated-AWQ-MTP"
CONTAINER="qwen38-abliterated-3090"
HOST_PORT="${HOST_PORT:-8080}"
HF_CACHE="${HF_CACHE:-$HOME/.cache/huggingface}"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

log() { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

# --- Preflight ---
log "Checking GPUs..."
if ! command -v nvidia-smi >/dev/null 2>&1; then
  die "nvidia-smi not found. Run this on the machine with your RTX 3090s (WSL2 + NVIDIA drivers)."
fi
GPU_COUNT="$(nvidia-smi -L | wc -l | tr -d ' ')"
nvidia-smi -L
if [[ "$GPU_COUNT" -lt 2 ]]; then
  echo "WARNING: expected 2 GPUs, found $GPU_COUNT. Edit docker-compose to use tensor-parallel-size 1."
fi

log "Checking Docker..."
if ! command -v docker >/dev/null 2>&1; then
  die "Docker not installed. On WSL2: install Docker Desktop and enable WSL integration."
fi
if ! docker info >/dev/null 2>&1; then
  die "Docker daemon not running."
fi
if ! docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi -L >/dev/null 2>&1; then
  die "NVIDIA Container Toolkit not working inside Docker."
fi

mkdir -p "$HF_CACHE"
export HF_CACHE
export HOST_PORT

# --- Optional: pre-download model weights (~16 GB) ---
if [[ "${SKIP_DOWNLOAD:-0}" != "1" ]]; then
  log "Pre-downloading $MODEL_ID to $HF_CACHE ..."
  if command -v huggingface-cli >/dev/null 2>&1; then
    huggingface-cli download "$MODEL_ID" --cache-dir "$HF_CACHE" ${HF_TOKEN:+--token "$HF_TOKEN"}
  elif python3 -c "import huggingface_hub" 2>/dev/null; then
    python3 - <<PY
from huggingface_hub import snapshot_download
import os
snapshot_download(repo_id="${MODEL_ID}", cache_dir=os.path.expanduser("${HF_CACHE}"),
                  token=os.environ.get("HF_TOKEN") or None)
PY
  else
    log "huggingface-cli not found — vLLM will download on first boot (slower)."
    pip3 install -q 'huggingface_hub[cli]' || true
    if command -v huggingface-cli >/dev/null 2>&1; then
      huggingface-cli download "$MODEL_ID" --cache-dir "$HF_CACHE" ${HF_TOKEN:+--token "$HF_TOKEN"}
    fi
  fi
fi

# --- Tailscale (optional but requested) ---
TAILSCALE_IP=""
if command -v tailscale >/dev/null 2>&1; then
  log "Tailscale detected."
  if ! tailscale status >/dev/null 2>&1; then
    log "Tailscale not logged in. Run: sudo tailscale up"
  else
    TAILSCALE_IP="$(tailscale ip -4 2>/dev/null || true)"
  fi
else
  log "Tailscale not installed in this environment."
  log "Install on Windows host: https://tailscale.com/download/windows"
  log "Or in WSL: curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up"
fi

# --- Launch vLLM ---
log "Pulling vLLM image..."
docker compose -f "$COMPOSE_FILE" pull

log "Stopping any previous container..."
docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true

log "Starting vLLM (both GPUs, MTP on, 262K context)..."
docker compose -f "$COMPOSE_FILE" up -d

log "Waiting for health (model load can take several minutes on first run)..."
for i in $(seq 1 120); do
  if curl -sf "http://127.0.0.1:${HOST_PORT}/v1/models" >/dev/null 2>&1; then
    break
  fi
  sleep 5
  if [[ "$((i % 6))" -eq 0 ]]; then
    echo "  still loading... ($(docker logs --tail 3 "$CONTAINER" 2>&1 | tail -1))"
  fi
done

# --- Verify MTP ---
log "Container log checks:"
docker logs "$CONTAINER" 2>&1 | rg -i "Detected MTP|KV cache|error|SpecDecoding" | tail -15 || docker logs --tail 20 "$CONTAINER"

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
WSL_HOST="$(grep nameserver /etc/resolv.conf 2>/dev/null | awk '{print $2}' | head -1)"

cat <<EOF

================================================================================
 vLLM is up
================================================================================
 Local (WSL):     http://127.0.0.1:${HOST_PORT}/v1
 Windows host:    http://localhost:${HOST_PORT}/v1
 LAN:             http://${LAN_IP:-?}:${HOST_PORT}/v1
 WSL gateway:     http://${WSL_HOST:-?}:${HOST_PORT}/v1  (try if localhost fails)
 Tailscale:       http://${TAILSCALE_IP:-<run tailscale ip -4>}:${HOST_PORT}/v1

 Model name:      qwen3.8-27b-abliterated

 Cursor / OpenAI client:
   Base URL:  http://<tailscale-ip>:${HOST_PORT}/v1
   API key:   not required (leave blank or use "local")

 Logs:            docker logs -f ${CONTAINER}
 Stop:            docker compose -f ${COMPOSE_FILE} down

 IMPORTANT:
   - Set temperature >= 0.6 (never 0) — greedy loops on this quant.
   - reasoning_effort defaults to medium in compose file.
   - Verify MTP loaded: docker logs ${CONTAINER} | rg "Detected MTP"
================================================================================
EOF
