# huihui-qwen3.8-27b-abliterated on dual RTX 3090
# Engine: ik_llama.cpp (best GGUF path for uncensored + dual GPU + max context)
# Override MODEL_PATH here if auto-detect fails.

$ErrorActionPreference = "Stop"

$Script:LocalLlmRoot = if ($env:LOCAL_LLM_ROOT) { $env:LOCAL_LLM_ROOT } else { "C:\local-llm" }
$Script:IkLlamaBinDir = Join-Path $LocalLlmRoot "ik-llama.cpp"
$Script:LlamaBinDir   = Join-Path $LocalLlmRoot "llama.cpp"   # fallback only
$Script:ModelsDir     = Join-Path $LocalLlmRoot "models"
$Script:LogsDir       = Join-Path $LocalLlmRoot "logs"

# Leave empty to auto-detect via find-model.ps1
$Script:ModelPath = ""

# OpenAI-compatible API (point Cursor here instead of LM Studio :1234)
$Script:ListenHost = "127.0.0.1"
$Script:Port = 8080

# Dual 3090: ik_llama graph split is faster than stock layer split for dense Qwen.
# Do NOT enable MTP on abliterated builds (draft head is broken).
$Script:GpuLayers       = 99
$Script:SplitMode       = "graph"    # ik_llama: graph | layer | none
$Script:TensorSplit     = "1,1"
$Script:MainGpu         = 0
$Script:CudaDevices     = "0,1"
$Script:DisableCudaGraphs = $true     # required for stable graph split on some models

# Max context with q8_0 KV (your preference). --fit on sizes context to VRAM.
$Script:ContextLength   = 0
$Script:KvCacheTypeK    = "q8_0"
$Script:KvCacheTypeV    = "q8_0"
$Script:UseFitParams    = $true
$Script:FlashAttention  = $true
$Script:BatchSize       = 2048
$Script:UbatchSize      = 512
$Script:ParallelSlots   = 1

# Abliterated GGUF: never enable speculative / MTP decoding.
$Script:EnableMtp       = $false

# ik_llama.cpp release to download (CUDA 12.8 + AVX2 = RTX 3090)
$Script:IkLlamaTag      = "main-b4608-b33a10d"
$Script:IkLlamaCuda     = "12.8"
$Script:IkLlamaCpu      = "avx2"
