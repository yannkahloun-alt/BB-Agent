param(
    [string]$BBData = 'C:\Program Files (x86)\Steam\steamapps\common\Battle Brothers\data',
    [string]$BBBuilder = 'C:\_dev\BBBuilder\BBBuilder.exe',
    [string]$ModsRoot = 'C:\_dev\BB-Mods'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Prod = Join-Path $ModsRoot 'bb_agent_combat_sandbox_prod'
$Oracle = Join-Path $ModsRoot 'bb_agent_combat_sandbox_oracle'
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

Remove-Item $Prod,$Oracle -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $Prod,$Oracle | Out-Null
Copy-Item (Join-Path $RepoRoot 'companion_mod\scripts') (Join-Path $Prod 'scripts') -Recurse
Copy-Item (Join-Path $RepoRoot 'companion_mod\debug_oracle\scripts') (Join-Path $Oracle 'scripts') -Recurse

& $BBBuilder build $Prod -rebuild -zipname mod_bb_agent_capture
if ($LASTEXITCODE -ne 0) { throw 'Production BBBuilder compile failed' }

& $BBBuilder build $Oracle -rebuild -zipname zz_bb_agent_debug_oracle
if ($LASTEXITCODE -ne 0) { throw 'DEBUG_ORACLE BBBuilder compile failed' }

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

if ($preload -notmatch 'Version = "0\.2\.25"') { throw 'Wrong BB-Agent companion version' }
if ($preload -notmatch 'runtime_combat_sandbox') { throw 'Full combat sandbox module missing' }
if ($preload -notmatch 'runtime_combat_sandbox_bounds') { throw 'Combat sandbox bounds module missing' }
if ($preload -notmatch 'runtime_combat_sandbox_continuity') { throw 'Combat sandbox continuity module missing' }
foreach ($forbidden in @(
    'runtime_combat_sandbox_incremental',
    'runtime_movement_sandbox',
    'runtime_debug_oracle_movement_compare',
    'runtime_debug_oracle_ally_jump_probe',
    'runtime_debug_oracle_route_score',
    'runtime_navigator_tiebreak_compat'
)) {
    if ($preload -match [regex]::Escape($forbidden)) {
        throw "Unexpected stale module in preload: $forbidden"
    }
}

Copy-Item $prodZip (Join-Path $BBData 'mod_bb_agent_capture.zip') -Force
Copy-Item (Join-Path $Oracle 'zz_bb_agent_debug_oracle.zip') `
    (Join-Path $BBData 'zz_bb_agent_debug_oracle.zip') -Force

$installed = @(Get-ChildItem $BBData -Recurse -File -Filter '*bb_agent*.zip')
if ($installed.Count -ne 2) {
    Write-Host 'Installed BB-Agent zips:'
    $installed | Select-Object FullName
    throw "Expected exactly 2 BB-Agent zips under data; found $($installed.Count)"
}

Write-Host ''
Write-Host 'FULL COMBAT SANDBOX INSTALLED'
Write-Host '  companion: 0.2.25'
Write-Host '  capture mode: staged tactical onUpdate (1 bounded record per update)'
Write-Host '  continuity: survives unchanged failed READY signatures'
Write-Host '  reflection budget: 2048 nodes per top-level reflection'
Write-Host '  logical record cap: 32768 decoded bytes'
Write-Host '  omniscient DEBUG snapshot: enabled by separate overlay'
Write-Host '  old path-comparison probes: absent'
Write-Host '  source commit:' $head
Write-Host ''
Write-Host 'Launch Battle Brothers and enter a fresh fight. Stop at the first active brother.'
