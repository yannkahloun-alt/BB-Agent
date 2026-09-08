param(
    [string]$Log = 'C:\Users\yannk\OneDrive\Documents\Battle Brothers\log.html',
    [string]$Out = ''
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Out) { $Out = Join-Path $RepoRoot 'production-ready-timing.json' }

powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File (Join-Path $PSScriptRoot 'install_live_production.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Production install failed' }

Remove-Item $Log -Force -ErrorAction SilentlyContinue
Remove-Item $Out -Force -ErrorAction SilentlyContinue

Start-Process 'steam://rungameid/365360'
Write-Host ''
Write-Host 'Enter ONE FRESH FIGHT and stop at the FIRST ACTIVE BROTHER.'
Write-Host 'This is a production-only validation: DEBUG_ORACLE is not installed.'
Write-Host ''

python (Join-Path $PSScriptRoot 'extract_live_ready_timing.py') `
    --log $Log `
    --out $Out `
    --wait-seconds 600
if ($LASTEXITCODE -ne 0) {
    throw 'No complete production DECISION_READY timing pair was captured. Preserve log.html.'
}

Write-Host ''
Write-Host 'PRODUCTION VALIDATION COMPLETE'
Write-Host 'Upload:'
Write-Host "  $Out"
