# Same as SETUP-3090.bat — run in PowerShell on your Windows 3090 PC:
#   irm https://raw.githubusercontent.com/tmophoto/sand_casting_v2/cursor/vllm-abliterated-3090-853d/SETUP-3090.ps1 | iex
$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/tmophoto/sand_casting_v2.git"
$Branch = "cursor/vllm-abliterated-3090-853d"
$Target = Join-Path $env:USERPROFILE "sand_casting_v2"

if (-not (Test-Path (Join-Path $Target ".git"))) {
    Write-Host "Cloning repo to $Target ..."
    git clone $RepoUrl $Target
}
Set-Location $Target
git fetch origin
git checkout $Branch
git pull origin $Branch

& (Join-Path $Target "scripts\vllm-3090\install-and-launch-tailscale.ps1")
