from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "companion_mod/scripts"
DEBUG = ROOT / "companion_debug_mod/scripts"
DEBUG_PRELOAD = DEBUG / "!mods_preload/mod_bb_agent_debug_oracle.nut"
DEBUG_RUNTIME = DEBUG / "bb_agent_debug_oracle/runtime_oracle.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_debug_oracle_is_physically_separate_from_production_companion() -> None:
    production = "\n".join(
        path.read_text(encoding="utf-8") for path in PRODUCTION.rglob("*.nut")
    )
    assert DEBUG_PRELOAD.is_file()
    assert DEBUG_RUNTIME.is_file()
    assert "BBAGENT_DebugOracle" not in production
    assert "bb_agent_debug_oracle" not in production
    assert "omniscient_debug" not in production


def test_debug_preload_extends_existing_capture_mod_without_mod_identity_change() -> None:
    preload = _text(DEBUG_PRELOAD)
    assert '::Hooks.hasMod("mod_bb_agent_capture")' in preload
    assert '::Hooks.getMod("mod_bb_agent_capture")' in preload
    assert "captureMod.queue(function()" in preload
    assert '::include("scripts/bb_agent_debug_oracle/runtime_oracle")' in preload
    assert "::Hooks.register(" not in preload


def test_debug_runtime_emits_only_explicit_omniscient_profile() -> None:
    runtime = _text(DEBUG_RUNTIME)
    assert 'record.information_profile <- "omniscient_debug";' in runtime
    assert "oracle_version = this.Version" in runtime
    assert "raw_source_fingerprint = wire.canonicalHash" in runtime
    assert "raw_actors = this._rawActors(_raw)" in runtime
    assert "raw_tiles = this._rawTiles()" in runtime
    assert '"[BB-Agent Oracle] READY battle="' in runtime
    assert 'information_profile <- "player_legal"' not in runtime


def test_debug_runtime_observes_production_without_executing_gameplay() -> None:
    runtime = _text(DEBUG_RUNTIME)
    assert "local originalReadyState = liveExport._readyState;" in runtime
    assert "local originalHandleLifecycleEvent = liveExport.handleLifecycleEvent;" in runtime
    assert "return originalReadyState.acall([this, _raw]);" in runtime
    assert "local result = originalHandleLifecycleEvent.acall([this, _event]);" in runtime
    assert "snapshot.production_last_error = capture.State.LastError;" in runtime
    assert "snapshot.production_ready_after_handle = capture.State.IsReady;" in runtime
    for forbidden in (
        ".travel(",
        "buildVisualisation(",
        "Math.rand(",
        "::Math.rand(",
        ".payForAction(",
        ".equip(",
        ".unequip(",
        ".swap(",
        ".use(",
        ".wait(",
        ".endTurn(",
    ):
        assert forbidden not in runtime


def test_debug_runtime_uses_native_and_projected_topology_side_by_side() -> None:
    runtime = _text(DEBUG_RUNTIME)
    assert "_tile.hasNextTile(direction)" in runtime
    assert "_tile.getNextTile(direction)" in runtime
    assert "projected_runtime_neighbor_ids = runtimeNeighbors" in runtime
    assert "projected_state_neighbors =" in runtime
    assert "from_in_projection = fromInProjection" in runtime
    assert "to_in_projection = toInProjection" in runtime
    assert "from_visible_in_projection" in runtime
    assert "to_visible_in_projection" in runtime
