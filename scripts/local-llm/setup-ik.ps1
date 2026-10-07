# Download ik_llama.cpp (recommended for abliterated GGUF + dual 3090).
param(
    [string]$Tag = "",
    [string]$CudaVersion = "",
    [string]$CpuVariant = ""
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\config.ps1"

$tag  = if ($Tag) { $Tag } else { $IkLlamaTag }
$cuda = if ($CudaVersion) { $CudaVersion } else { $IkLlamaCuda }
$cpu  = if ($CpuVariant) { $CpuVariant } else { $IkLlamaCpu }

New-Item -ItemType Directory -Force -Path $LocalLlmRoot, $ModelsDir, $LogsDir | Out-Null

$binZip = "ik_llama-$tag-bin-win-cuda-$cuda-x64-$cpu.zip"
$rtZip  = "ik_llama-cudart-$tag-bin-win-cuda-$cuda-x64-$cpu.zip"
$base   = "https://github.com/Thireus/ik_llama.cpp/releases/download/$tag"
$stage  = Join-Path $LocalLlmRoot "stage-$tag-cuda-$cuda"

function Ensure-Download($name) {
    $dest = Join-Path $LocalLlmRoot $name
    if (-not (Test-Path $dest)) {
        Write-Host "Downloading $name ..."
        Invoke-WebRequest -Uri "$base/$name" -OutFile $dest
    }
    return $dest
}

$binPath = Ensure-Download $binZip
$rtPath  = Ensure-Download $rtZip

if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Expand-Archive -Path $binPath -DestinationPath $stage -Force
Expand-Archive -Path $rtPath  -DestinationPath $stage -Force

if (Test-Path $IkLlamaBinDir) { Remove-Item -Recurse -Force $IkLlamaBinDir }
New-Item -ItemType Directory -Force -Path $IkLlamaBinDir | Out-Null
Copy-Item -Path (Join-Path $stage "*") -Destination $IkLlamaBinDir -Recurse -Force

$server = Join-Path $IkLlamaBinDir "llama-server.exe"
if (-not (Test-Path $server)) {
    throw "llama-server.exe not found. Check tag $tag or try -CudaVersion 13.1"
}

Write-Host "ik_llama.cpp ready: $server"
Write-Host ""
Write-Host "1) Optional: .\estimate-context.ps1"
Write-Host "2) Start:        .\start-max-context.ps1"
