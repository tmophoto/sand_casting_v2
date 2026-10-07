# Download a CUDA llama.cpp build and prepare folders for dual-GPU serving.
param(
    [string]$LlamaVersion = "b11433",
    [ValidateSet("12.4", "13.4")]
    [string]$CudaVersion = "12.4"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\config.ps1"

New-Item -ItemType Directory -Force -Path $LocalLlmRoot, $ModelsDir, $LogsDir | Out-Null

$binZip  = "llama-$LlamaVersion-bin-win-cuda-$CudaVersion-x64.zip"
$rtZip   = "cudart-llama-bin-win-cuda-$CudaVersion-x64.zip"
$baseUrl = "https://github.com/ggml-org/llama.cpp/releases/download/$LlamaVersion"
$stage   = Join-Path $LocalLlmRoot "stage-$LlamaVersion-cuda-$CudaVersion"

function Ensure-Download($name) {
    $dest = Join-Path $LocalLlmRoot $name
    if (-not (Test-Path $dest)) {
        Write-Host "Downloading $name ..."
        Invoke-WebRequest -Uri "$baseUrl/$name" -OutFile $dest
    }
    return $dest
}

$binPath = Ensure-Download $binZip
$rtPath  = Ensure-Download $rtZip

if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Expand-Archive -Path $binPath -DestinationPath $stage -Force
Expand-Archive -Path $rtPath  -DestinationPath $stage -Force

if (Test-Path $LlamaBinDir) { Remove-Item -Recurse -Force $LlamaBinDir }
New-Item -ItemType Directory -Force -Path $LlamaBinDir | Out-Null
Copy-Item -Path (Join-Path $stage "*") -Destination $LlamaBinDir -Recurse -Force

$server = Join-Path $LlamaBinDir "llama-server.exe"
if (-not (Test-Path $server)) {
    throw "llama-server.exe not found after extract. Try a different -CudaVersion (12.4 vs 13.4)."
}

Write-Host "llama.cpp ready: $server"
Write-Host "CUDA runtime:    $CudaVersion"
Write-Host ""
Write-Host "For abliterated GGUF on dual 3090, prefer ik_llama instead:"
Write-Host "  .\setup-ik.ps1"
Write-Host ""
Write-Host "Stock llama.cpp fallback:"
Write-Host "  .\estimate-context.ps1"
Write-Host "  .\start-max-context.ps1 -UseStockLlama"
