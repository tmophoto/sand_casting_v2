# Start abliterated Qwen3.8-27B on 2× RTX 3090 via vLLM (Docker on WSL2).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$wsl = Get-Command wsl -ErrorAction SilentlyContinue
if (-not $wsl) {
    Write-Host @"
This stack runs vLLM in Docker. On Windows, use WSL2:

  wsl
  cd /mnt/c/path/to/sand_casting_v2/scripts/vllm-3090
  ./start.sh

Or install Docker Desktop with WSL2 backend + GPU support, then:
  docker compose up -d
"@
    exit 1
}

Write-Host "Launching via WSL..."
wsl -e bash -lc "cd '$(wsl wslpath -a $PSScriptRoot)' && chmod +x start.sh && ./start.sh"
