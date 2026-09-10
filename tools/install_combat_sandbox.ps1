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

if ($preload -notmatch 'Version = "0\.2\.42"') { throw 'Wrong BB-Agent companion version' }
if ($preload -notmatch 'runtime_player_legal_blocking_compat') { throw 'Player-legal blocker projection missing' }
if ($preload -notmatch 'runtime_player_legal_actor_enumeration_compat') { throw 'Player-legal actor enumeration compatibility missing' }
if ($preload -notmatch 'runtime_player_legal_turn_list_fastpath') { throw 'Player-legal turn-list fast path missing' }
if ($preload -notmatch 'runtime_movement_graph_compat') { throw 'Movement reachability graph missing' }
if ($preload -notmatch 'runtime_movement_ally_jump_cost_compat') { throw 'Ally-jump movement cost compatibility missing' }
if ($preload -notmatch 'runtime_movement_blocking_compat') { throw 'Movement blocker compatibility missing' }
if ($preload -notmatch 'runtime_combat_sandbox') { throw 'Full combat sandbox module missing' }
if ($preload -notmatch 'runtime_combat_sandbox_discovery') { throw 'Combat sandbox discovery module missing' }
if ($preload -notmatch 'runtime_combat_sandbox_fidelity') { throw 'Combat sandbox fidelity module missing' }
if ($preload -notmatch 'runtime_combat_sandbox_reference_fields') { throw 'Combat sandbox reference-field layer missing' }
if ($preload -notmatch 'runtime_combat_sandbox_nested_fields') { throw 'Combat sandbox nested-field layer missing' }
if ($preload -notmatch 'runtime_combat_sandbox_oracle_first') { throw 'Oracle-first sandbox module missing' }
if ($preload -notmatch 'runtime_combat_sandbox_player_legal_phase') { throw 'True post-oracle PLAYER_LEGAL phase missing' }
if ($preload -notmatch 'runtime_combat_sandbox_bounds') { throw 'Combat sandbox bounds module missing' }
if ($preload -notmatch 'runtime_combat_sandbox_continuity') { throw 'Combat sandbox continuity module missing' }
if ($preload -notmatch 'runtime_combat_sandbox_recovery') { throw 'Combat sandbox recovery module missing' }
if ($preload -notmatch 'runtime_debug_oracle_ally_jump_probe') { throw 'Ally-jump oracle probe missing' }
if ($preload -notmatch 'runtime_debug_oracle_ally_jump_roster_probe') { throw 'Roster ally-jump oracle probe missing' }
if ($preload -notmatch 'runtime_debug_oracle_movement_validation') { throw 'Staged native movement validation missing' }
if ($preload -notmatch 'runtime_debug_oracle_movement_validation_fatigue') { throw 'Native movement fatigue-semantics validation missing' }
if ($preload -notmatch 'runtime_debug_oracle_movement_validation_legality') { throw 'Native movement legality validation missing' }
if ($preload -notmatch 'runtime_debug_oracle_movement_validation_geometry') { throw 'Native movement geometry validation missing' }
if ($preload -notmatch 'runtime_debug_oracle_movement_validation_remembered') { throw 'Remembered-terrain movement validation missing' }
foreach ($forbidden in @(
    'runtime_combat_sandbox_incremental',
    'runtime_movement_sandbox',
    'runtime_debug_oracle_movement_compare',
    'runtime_debug_oracle_route_score',
    'runtime_navigator_tiebreak_compat',
    'runtime_debug_oracle_tiebreak_samples',
    'runtime_debug_oracle_path_anchors'
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
Write-Host '  companion: 0.2.42'
Write-Host '  capture mode: true two-phase oracle-first staged discovery + capture'
Write-Host '  player-legal projection: released only after the omniscient sandbox queue drains'
Write-Host '  player-legal actors: tactical turn-list source; no native EntityManager.getAllInstances scan'
Write-Host '  movement reachability: player-known Pareto AP/fatigue labels, no native pathfinder'
Write-Host '  ally-jump movement cost: sum of both constituent movement steps'
Write-Host '  visible blockers: exact only on currently visible tiles; remembered occupancy unknown'
Write-Host '  hidden occupancy: never inspected by production blocker/movement graph layers'
Write-Host '  ally-jump probe: one DEBUG_ORACLE native sample, roster-scanned when active has no candidate'
Write-Host '  native movement validation: <=6 exact-visible + <=2 remembered DEBUG samples, one native call per update'
Write-Host '  native validation split: legality, resource reachability, preview cost, fatigue semantics'
Write-Host '  native geometry summary: model/native tile-count plus first/end endpoint comparison'
Write-Host '  remembered scope: reuses incremental tile discovery; no extra full-map scan'
Write-Host '  native fatigue semantics: compare path-search fatigue and execution fatigue independently'
Write-Host '  duplicate runtime collections: summarized as bounded actor/skill/item references'
Write-Host '  duplicate/error-prone runtime backrefs: summarized as actor/skill/tile/value references'
Write-Host '  unique large fields: recursively sharded with deterministic nested owner identities'
Write-Host '  AI known-opponents: actor/tile/TTL references instead of duplicate actor graphs'
Write-Host '  runtime scaffolding: summarized, not emitted as per-field jobs'
Write-Host '  fidelity: state data split into independently bounded field records'
Write-Host '  continuity: survives unchanged failed READY signatures'
Write-Host '  reflection budget: 2048 nodes per field reflection with bounded recovery'
Write-Host '  logical record cap: 32768 decoded bytes'
Write-Host '  extraction: quality + native comparison + PLAYER_LEGAL timing metadata in one JSON'
Write-Host '  omniscient DEBUG snapshot: enabled by separate overlay'
Write-Host '  normal live export while DEBUG_ORACLE is enabled: suppressed'
Write-Host '  source commit:' $head
Write-Host ''
Write-Host 'Launch Battle Brothers and enter a fresh fight. Stop at the first active brother.'
