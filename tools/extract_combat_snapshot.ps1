param(
    [string]$Log = 'C:\Users\yannk\OneDrive\Documents\Battle Brothers\log.html',
    [string]$Out = 'C:\_dev\BB-Agent\combat-sandbox-latest.json',
    [int]$WaitSeconds = 60
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot

py -3.12 (Join-Path $RepoRoot 'tools\extract_combat_snapshot.py') `
    --log $Log `
    --out $Out `
    --wait-seconds $WaitSeconds `
    --poll-seconds 0.25
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host "Upload this file: $Out"
