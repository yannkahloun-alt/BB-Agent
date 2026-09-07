param(
    [string]$Log = 'C:\Users\yannk\OneDrive\Documents\Battle Brothers\log.html',
    [string]$Out = 'C:\_dev\BB-Agent\combat-sandbox-latest.json'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot

py -3.12 (Join-Path $RepoRoot 'tools\extract_combat_snapshot.py') --log $Log --out $Out
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host "Upload this file: $Out"
