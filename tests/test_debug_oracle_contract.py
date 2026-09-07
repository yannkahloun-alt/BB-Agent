from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
ORACLE = ROOT / "companion_mod/scripts/bb_agent/debug_oracle.nut"
DEBUG_ENABLE = (
    ROOT
    / "companion_mod/debug_oracle/scripts/!mods_preload/00_bb_agent_debug_oracle.nut"
)
EXPORT = ROOT / "companion_mod/scripts/bb_agent/live_export.nut"
PROJECTION = ROOT / "companion_mod/scripts/bb_agent/player_legal_projection.nut"
COMPAT = ROOT / "companion_mod/scripts/bb_agent/runtime_navigator_path_compat.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_debug_oracle_is_off_in_normal_companion() -> None:
    oracle = _text(ORACLE)
    preload = _text(PRELOAD)
    assert "root.BBAGENT_DEBUG_ORACLE <- false;" in oracle
    assert "Enabled = root.BBAGENT_DEBUG_ORACLE == true" in oracle
    assert "scripts/bb_agent/debug_oracle" in preload
    assert not (
        ROOT / "companion_mod/scripts/!mods_preload/00_bb_agent_debug_oracle.nut"
    ).exists()


def test_debug_oracle_requires_explicit_separate_overlay() -> None:
    enable = _text(DEBUG_ENABLE)
    assert "BBAGENT_DEBUG_ORACLE = true" in enable
    assert "BBAGENT_DEBUG_ORACLE <- true" in enable
    assert "[BB-Agent Oracle]" in enable
    assert "DEBUG_ORACLE explicitly enabled" in enable


def test_oracle_is_diagnostic_only_and_not_a_wire_profile() -> None:
    oracle = _text(ORACLE)
    export = _text(EXPORT)
    projection = _text(PROJECTION)

    assert '::logInfo("[BB-Agent Oracle] " + _message);' in oracle
    for forbidden in (
        "BBAGENT1|",
        "encodeFrame(",
        "DECISION_ORACLE",
        "omniscient_debug",
        "information_profile",
        "record.payload",
    ):
        assert forbidden not in oracle

    assert 'record.information_profile <- "player_legal"' in export
    assert "omniscient_debug" not in export
    assert "BBAGENT_DEBUG_ORACLE" not in projection
    assert "BBAGENT_DebugOracle" not in projection


def test_movement_oracle_remains_bounded_for_native_comparison() -> None:
    oracle = _text(ORACLE)
    for token in (
        "MaxLogLines = 96",
        "MaxBudget = 32",
        "MaxPathEntries = 24",
        "MovementMismatchCaptured = false",
        "mode=DEBUG_ORACLE event=movement_topology_mismatch",
        "full_native ",
        "cost_field label=",
        "budget=",
        "native_neighbor direction=",
        "native_two_step_bridge_count=",
        "navigator_path_slots_found=",
    ):
        assert token in oracle


def test_private_native_path_introspection_is_confined_to_oracle_module() -> None:
    oracle = _text(ORACLE)
    compat = _text(COMPAT)

    for token in (
        "_navigator.getPath()",
        "_navigator.Path",
        "_navigator.m.Path",
        "_navigator.m.PathTiles",
        "_navigator.m.CurrentPath",
        "_navigator.m.PathResult",
        "_navigator.m.Nodes",
        "_navigator.getCurrentPath()",
        "_navigator.getPathTiles()",
        "_navigator.getPathNodes()",
    ):
        assert token in oracle

    assert "navigator.findPath(" not in compat
    assert "navigator.getCostForPath(" not in compat
    assert "native_find_path_calls=0" in compat
    assert "movement_tree reachable=" in compat


def test_oracle_reads_native_tiles_without_instance_membership_assumptions() -> None:
    oracle = _text(ORACLE)
    assert "runtimeId = _tile.ID.tostring();" in oracle
    assert 'square = _tile.SquareCoords.X + ":" + _tile.SquareCoords.Y;' in oracle
    assert 'if ("ID" in _tile)' not in oracle
    assert 'if ("SquareCoords" in _tile)' not in oracle
