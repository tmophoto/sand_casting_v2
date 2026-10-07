# Start huihui-qwen3.8-27b-abliterated on dual RTX 3090 with maximum context.
param(
    [string]$ModelPathOverride = "",
    [int]$PortOverride = 0,
    [int]$ContextOverride = 0,
    [switch]$EstimateOnly
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\config.ps1"

$server = Join-Path $LlamaBinDir "llama-server.exe"
if (-not (Test-Path $server)) {
    Write-Host "llama-server not found. Run: .\setup.ps1"
    exit 1
}

$model = if ($ModelPathOverride) { $ModelPathOverride } elseif ($Script:ModelPath) { $Script:ModelPath } else { & "$PSScriptRoot\find-model.ps1" }
if (-not (Test-Path $model)) {
    throw "Model not found: $model"
}

$port = if ($PortOverride -gt 0) { $PortOverride } else { $Script:Port }
$ctx  = if ($ContextOverride -gt 0) { $ContextOverride } else { $Script:ContextLength }

$logFile = Join-Path $LogsDir ("server-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date))
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

$args = @(
    "-m", $model,
    "--host", $ListenHost,
    "--port", "$port",
    "-ngl", "$GpuLayers",
    "-sm", $SplitMode,
    "-ts", $TensorSplit,
    "-mg", "$MainGpu",
    "--cache-type-k", $KvCacheTypeK,
    "--cache-type-v", $KvCacheTypeV,
    "-b", "$BatchSize",
    "-ub", "$UbatchSize",
    "-np", "$ParallelSlots",
    "--jinja",
    "--alias", "huihui-qwen3.8-27b-abliterated"
)

if ($FlashAttention) { $args += @("-fa", "on") }
if ($UseFitParams -and $ctx -le 0) { $args += @("--fit", "on") }
elseif ($ctx -gt 0) { $args += @("-c", "$ctx") }
else { $args += @("-c", "131072") }

if ($EstimateOnly) { $args += "--estimate-only" }

$env:CUDA_VISIBLE_DEVICES = $CudaDevices

Write-Host "Model:   $model"
Write-Host "API:     http://${ListenHost}:$port/v1"
Write-Host "GPUs:    $CudaDevices  split=$SplitMode  ts=$TensorSplit"
Write-Host "Context: $(if ($UseFitParams -and $ctx -le 0) { 'auto (--fit on)' } else { $ctx })"
Write-Host "KV:      k=$KvCacheTypeK v=$KvCacheTypeV"
Write-Host "MTP:     OFF (abliterated model)"
Write-Host "Log:     $logFile"
Write-Host ""

if ($EstimateOnly) {
    & $server @args
    exit $LASTEXITCODE
}

# Tee logs for debugging offload layer counts / fitted context.
& $server @args 2>&1 | Tee-Object -FilePath $logFile
