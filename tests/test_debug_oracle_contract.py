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


def test_oracle_substrate_is_bounded_and_not_a_wire_profile() -> None:
    oracle = _text(ORACLE)
    export = _text(EXPORT)
    projection = _text(PROJECTION)

    for required in (
        "MaxLogLines = 96",
        "LogLines = 0",
        "if (this.LogLines >= this.MaxLogLines) return;",
        '::logInfo("[BB-Agent Oracle] " + _message);',
        "substrate_loaded enabled=",
    ):
        assert required in oracle

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


def test_retired_native_path_introspection_is_absent_from_shared_substrate() -> None:
    oracle = _text(ORACLE)
    for forbidden in (
        "MaxBudget",
        "MaxPathEntries",
        "MovementMismatchCaptured",
        "NavigatorPathSlots",
        "reportMovementTopologyMismatch",
        "_probeNavigatorInternals",
        "_dumpCostFields",
        "_dumpPathValue",
        "_dumpNativeNeighbors",
        "_dumpTwoStepBridges",
        "getCostForPath(",
        "getPath()",
        "getCurrentPath()",
        "getPathTiles()",
        "getPathNodes()",
    ):
        assert forbidden not in oracle


def test_production_movement_still_has_zero_native_pathfinder_calls() -> None:
    compat = _text(COMPAT)
    assert "navigator.findPath(" not in compat
    assert "navigator.getCostForPath(" not in compat
    assert "native_find_path_calls=0" in compat
    assert "movement_tree reachable=" in compat
