# Print the largest context llama.cpp can fit with current dual-GPU settings.
$ErrorActionPreference = "Stop"
& "$PSScriptRoot\start-max-context.ps1" -EstimateOnly
