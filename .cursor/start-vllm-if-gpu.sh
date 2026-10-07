#!/usr/bin/env bash
# Auto-start vLLM when a cloud agent boots on a GPU machine (private worker).
# No-op on Cursor's generic cloud VMs (no nvidia-smi / no docker).
set -euo pipefail

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "[start-vllm] No GPU — skipping vLLM (expected on generic cloud VMs)."
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[start-vllm] docker not found — install Docker on this worker machine."
  exit 0
fi

SCRIPT="$PWD/scripts/vllm-3090/install-and-launch-tailscale.sh"
if [[ ! -x "$SCRIPT" ]]; then
  chmod +x "$SCRIPT" 2>/dev/null || true
fi
if [[ ! -f "$SCRIPT" ]]; then
  echo "[start-vllm] $SCRIPT missing — pull latest repo."
  exit 0
fi

if curl -sf http://127.0.0.1:8080/v1/models >/dev/null 2>&1; then
  echo "[start-vllm] vLLM already running on :8080"
  exit 0
fi

echo "[start-vllm] GPU machine detected — launching vLLM in background..."
nohup bash "$SCRIPT" >> /tmp/cursor/vllm-start.log 2>&1 &
echo "[start-vllm] Log: /tmp/cursor/vllm-start.log"
