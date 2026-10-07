#!/usr/bin/env bash
# WSL2 / Linux dual-3090 launcher with max context (abliterated GGUF, no MTP).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_LLM_ROOT="${LOCAL_LLM_ROOT:-$HOME/local-llm}"
LLAMA_BIN="${LLAMA_BIN:-$LOCAL_LLM_ROOT/llama.cpp}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
CUDA_DEVICES="${CUDA_DEVICES:-0,1}"

find_model() {
  local roots=(
    "$HOME/.lmstudio/models"
    "$HOME/.cache/lm-studio/models"
    "$HOME/Downloads"
    "$HOME/models"
    "$LOCAL_LLM_ROOT/models"
    "$SCRIPT_DIR/models"
  )
  local f
  for root in "${roots[@]}"; do
    [[ -d "$root" ]] || continue
    f=$(find "$root" -iname '*huihui*qwen*abliterated*.gguf' -type f 2>/dev/null | head -1)
    [[ -n "$f" ]] && { echo "$f"; return 0; }
    f=$(find "$root" -iname '*huihui*qwen*.gguf' -type f 2>/dev/null | head -1)
    [[ -n "$f" ]] && { echo "$f"; return 0; }
  done
  return 1
}

MODEL="${MODEL_PATH:-}"
if [[ -z "$MODEL" ]]; then
  MODEL="$(find_model)" || { echo "Set MODEL_PATH to your .gguf"; exit 1; }
fi
[[ -f "$MODEL" ]] || { echo "Model not found: $MODEL"; exit 1; }

SERVER="$LLAMA_BIN/llama-server"
[[ -x "$SERVER" ]] || SERVER="$(command -v llama-server || true)"
[[ -n "$SERVER" ]] || { echo "Install llama.cpp CUDA build into $LLAMA_BIN"; exit 1; }

mkdir -p "$LOCAL_LLM_ROOT/logs"
LOG="$LOCAL_LLM_ROOT/logs/server-$(date +%Y%m%d-%H%M%S).log"

export CUDA_VISIBLE_DEVICES="$CUDA_DEVICES"

echo "Model:   $MODEL"
echo "API:     http://$HOST:$PORT/v1"
echo "GPUs:    $CUDA_DEVICES (layer split 1,1)"
echo "Context: auto (--fit on) with q4_0 KV cache"
echo "Log:     $LOG"
echo

exec "$SERVER" \
  -m "$MODEL" \
  --host "$HOST" --port "$PORT" \
  -ngl 99 -sm layer -ts 1,1 -mg 0 \
  -fa on --fit on \
  --cache-type-k q4_0 --cache-type-v q4_0 \
  -b 2048 -ub 512 -np 1 \
  --jinja \
  --alias huihui-qwen3.8-27b-abliterated \
  2>&1 | tee "$LOG"
