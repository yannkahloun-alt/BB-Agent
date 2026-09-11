param(
    [string]$BBData = 'C:\Program Files (x86)\Steam\steamapps\common\Battle Brothers\data',
    [string]$BBBuilder = 'C:\_dev\BBBuilder\BBBuilder.exe',
    [string]$ModsRoot = 'C:\_dev\BB-Mods'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Prod = Join-Path $ModsRoot 'bb_agent_live_production'
$Archive = Join-Path $RepoRoot '_archived-bb-agent-zips'

Get-Process BattleBrothers -ErrorAction SilentlyContinue | Stop-Process -Force
$head = (git -C $RepoRoot rev-parse HEAD).Trim()
Write-Host "Source commit: $head"

git -C $RepoRoot submodule update --init --recursive --force

New-Item -ItemType Directory -Path $Archive -Force | Out-Null
Get-ChildItem $BBData -Recurse -File -Filter '*bb_agent*.zip' -ErrorAction SilentlyContinue |
    ForEach-Object {
        $relative = $_.FullName.Substring($BBData.Length).TrimStart('\')
        $safeName = $relative -replace '[\\/: ]', '_'
        Move-Item $_.FullName (Join-Path $Archive $safeName) -Force
    }

Remove-Item $Prod -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $Prod | Out-Null
Copy-Item (Join-Path $RepoRoot 'companion_mod\scripts') (Join-Path $Prod 'scripts') -Recurse

& $BBBuilder build $Prod -rebuild -zipname mod_bb_agent_capture
if ($LASTEXITCODE -ne 0) { throw 'Production BBBuilder compile failed' }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$prodZip = Join-Path $Prod 'mod_bb_agent_capture.zip'
$zip = [System.IO.Compression.ZipFile]::OpenRead($prodZip)
try {
    $entry = $zip.Entries |
        Where-Object { $_.FullName -match 'mod_bb_agent_capture\.nut$' } |
        Select-Object -First 1
    if (-not $entry) { throw 'Capture preload missing from built zip' }
    $reader = New-Object System.IO.StreamReader($entry.Open())
    try { $preload = $reader.ReadToEnd() } finally { $reader.Dispose() }
} finally {
    $zip.Dispose()
}

if ($preload -notmatch 'Version = "0\.2\.44"') { throw 'Wrong BB-Agent companion version' }
if ($preload -notmatch 'runtime_player_legal_numeric_compat') {
    throw 'PLAYER_LEGAL numeric compatibility layer missing'
}
if ($preload -notmatch 'runtime_live_ready_timing') { throw 'Production READY timing layer missing' }
if ($preload -notmatch '(?s)player_legal_hardening.*runtime_player_legal_numeric_compat.*canonical_identity') {
    throw 'PLAYER_LEGAL numeric compatibility layer must load after hardening and before canonical identity'
}
if ($preload -notmatch '(?s)runtime_ready_failure_latch.*runtime_live_ready_timing') {
    throw 'READY timing layer must load after failure latch'
}

Copy-Item $prodZip (Join-Path $BBData 'mod_bb_agent_capture.zip') -Force
$installed = @(Get-ChildItem $BBData -Recurse -File -Filter '*bb_agent*.zip')
if ($installed.Count -ne 1 -or $installed[0].Name -ne 'mod_bb_agent_capture.zip') {
    Write-Host 'Installed BB-Agent zips:'
    $installed | Select-Object FullName
    throw 'Production validation requires exactly one BB-Agent production zip and no DEBUG overlay'
}

Write-Host ''
Write-Host 'BB-AGENT PRODUCTION LIVE VALIDATION INSTALLED'
Write-Host '  companion: 0.2.44'
Write-Host '  DEBUG_ORACLE overlay: NOT installed'
Write-Host '  PLAYER_LEGAL numeric normalization: source-proven whole numbers only'
Write-Host '  READY timing: production DECISION_READY path only'
Write-Host '  source commit:' $head
