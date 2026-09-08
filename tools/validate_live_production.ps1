param(
    [string]$Log = 'C:\Users\yannk\OneDrive\Documents\Battle Brothers\log.html',
    [string]$Out = ''
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Out) { $Out = Join-Path $RepoRoot 'production-ready-timing.json' }
$head = (git -C $RepoRoot rev-parse HEAD).Trim()

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
$extractExit = $LASTEXITCODE

$timing = $null
if (Test-Path $Out) {
    $timing = Get-Content $Out -Raw | ConvertFrom-Json
    $timing | Add-Member -NotePropertyName source_commit -NotePropertyValue $head
    $timing | Add-Member -NotePropertyName companion_version -NotePropertyValue '0.2.38'
    $timing | Add-Member -NotePropertyName debug_oracle_enabled -NotePropertyValue $false
    $timing | ConvertTo-Json -Depth 8 | Set-Content $Out -Encoding UTF8
}

if ($extractExit -ne 0) {
    if ($null -ne $timing -and $timing.success -eq $false) {
        throw "Production DECISION_READY failed at stage=$($timing.failure_stage). Timing JSON preserved: $Out"
    }
    if ($null -ne $timing) {
        throw "No complete production DECISION_READY timing pair was captured. Diagnostic JSON preserved: $Out"
    }
    throw 'No complete production DECISION_READY timing pair was captured. Preserve log.html.'
}

Write-Host ''
Write-Host 'PRODUCTION VALIDATION COMPLETE'
Write-Host 'Upload:'
Write-Host "  $Out"
