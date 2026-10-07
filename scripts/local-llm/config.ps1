# Dual RTX 3090 + max-context defaults for huihui-qwen3.8-27b-abliterated
# Override MODEL_PATH here if auto-detect fails.

$ErrorActionPreference = "Stop"

$Script:LocalLlmRoot = if ($env:LOCAL_LLM_ROOT) { $env:LOCAL_LLM_ROOT } else { "C:\local-llm" }
$Script:LlamaBinDir   = Join-Path $LocalLlmRoot "llama.cpp"
$Script:ModelsDir     = Join-Path $LocalLlmRoot "models"
$Script:LogsDir       = Join-Path $LocalLlmRoot "logs"

# Leave empty to auto-detect via find-model.ps1
$Script:ModelPath = ""

# OpenAI-compatible API (point Cursor / agents here instead of LM Studio :1234)
$Script:ListenHost = "127.0.0.1"
$Script:Port = 8080

# Dual 3090: layer split across both cards. Do NOT enable MTP on abliterated builds.
$Script:GpuLayers      = 99
$Script:SplitMode       = "layer"     # layer | row
$Script:TensorSplit     = "1,1"       # equal split across GPU 0 and GPU 1
$Script:MainGpu         = 0
$Script:CudaDevices     = "0,1"

# Max context: q8_0 KV cache (higher quality than q4_0; uses more VRAM).
# --fit on asks llama.cpp to pick the largest safe context for your VRAM.
$Script:ContextLength   = 0           # 0 = use --fit on; set e.g. 131072 to pin manually
$Script:KvCacheTypeK    = "q8_0"
$Script:KvCacheTypeV    = "q8_0"
$Script:UseFitParams    = $true       # auto-maximize context to available VRAM
$Script:FlashAttention  = $true
$Script:BatchSize       = 2048
$Script:UbatchSize      = 512
$Script:ParallelSlots   = 1           # keep 1 for max context per request

# Abliterated GGUF: MTP head is broken — never enable speculative decoding.
$Script:EnableMtp       = $false
