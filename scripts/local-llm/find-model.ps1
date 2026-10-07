# Find huihui-qwen3.8-27b-abliterated GGUF in common LM Studio / local paths.
param(
    [string]$Pattern = "*huihui*qwen*abliterated*.gguf"
)

$searchRoots = @(
    "$env:USERPROFILE\.lmstudio\models",
    "$env:USERPROFILE\.cache\lm-studio\models",
    "$env:LOCALAPPDATA\LM Studio\models",
    "$env:USERPROFILE\Downloads",
    "$env:USERPROFILE\models",
    "$env:USERPROFILE\local-llm\models",
    "C:\local-llm\models",
    (Join-Path $PSScriptRoot "models")
) | Where-Object { $_ -and (Test-Path $_) }

$candidates = @()
foreach ($root in $searchRoots) {
    $candidates += Get-ChildItem -Path $root -Recurse -Filter $Pattern -File -ErrorAction SilentlyContinue
}

if (-not $candidates) {
    # Broader fallback: any huihui qwen gguf
    foreach ($root in $searchRoots) {
        $candidates += Get-ChildItem -Path $root -Recurse -Filter "*huihui*qwen*.gguf" -File -ErrorAction SilentlyContinue
    }
}

if (-not $candidates) {
    Write-Error "No GGUF found. Searched:`n$($searchRoots -join "`n")`n`nSet MODEL_PATH manually in config.ps1"
    exit 1
}

# Prefer Q4_K_M for speed+context balance; else highest quant that isn't huge.
$ranked = $candidates | Sort-Object {
    $n = $_.Name.ToLower()
    if ($n -match 'q4_k_m') { 0 }
    elseif ($n -match 'q4_k_xl|ud-q4') { 1 }
    elseif ($n -match 'q5_k') { 2 }
    elseif ($n -match 'q6_k') { 3 }
    elseif ($n -match 'q8') { 4 }
    else { 5 }
}, { $_.LastWriteTime } -Descending

$best = $ranked | Select-Object -First 1
Write-Output $best.FullName
