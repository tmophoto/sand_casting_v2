# Run the full vLLM + Tailscale setup on your Windows GPU machine via WSL2.
# Right-click -> Run in PowerShell, or:
#   powershell -ExecutionPolicy Bypass -File install-and-launch-tailscale.ps1
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WslPath = wsl wslpath -a $ScriptDir

Write-Host "=== vLLM abliterated Qwen3.8-27B + Tailscale setup ==="
Write-Host ""

# Tailscale on Windows (for remote access to the exposed port)
$ts = Get-Command tailscale -ErrorAction SilentlyContinue
if ($ts) {
    $tsIp = & tailscale ip -4 2>$null
    if ($tsIp) {
        Write-Host "Windows Tailscale IP: $tsIp"
    } else {
        Write-Host "Tailscale installed but not connected. Run: tailscale up"
    }
} else {
    Write-Host "Install Tailscale on Windows: https://tailscale.com/download/windows"
}

# Allow inbound port 8080 for Tailscale/LAN (requires admin)
$port = 8080
$ruleName = "vLLM Qwen38 Abliterated $port"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host "Creating Windows Firewall rule for TCP $port (may prompt for admin)..."
    try {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow `
            -Protocol TCP -LocalPort $port -Profile Any | Out-Null
        Write-Host "Firewall rule created."
    } catch {
        Write-Host "Could not create firewall rule (run PowerShell as Administrator): $_"
    }
}

Write-Host ""
Write-Host "Starting install in WSL2..."
wsl -e bash -lc "cd '$WslPath' && chmod +x install-and-launch-tailscale.sh && ./install-and-launch-tailscale.sh"

Write-Host ""
Write-Host "If Tailscale is on Windows, connect from other devices to:"
Write-Host "  http://<your-windows-tailscale-ip>:8080/v1"
