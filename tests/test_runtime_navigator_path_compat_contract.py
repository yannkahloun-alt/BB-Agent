from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
COMPAT = ROOT / "companion_mod/scripts/bb_agent/runtime_navigator_path_compat.nut"
PINNED = "162f498ac7c49b4c317bbf54718a595ecef6a65a"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_load_order() -> None:
    preload = _text(PRELOAD)
    hardening = "scripts/bb_agent/affordance_export_hardening"
    oracle = "scripts/bb_agent/debug_oracle"
    compat = "scripts/bb_agent/runtime_navigator_path_compat"
    export = "scripts/bb_agent/live_export"
    assert (
        preload.index(hardening)
        < preload.index(oracle)
        < preload.index(compat)
        < preload.index(export)
    )


def test_single_native_cost_result_drives_path_reconstruction() -> None:
    text = _text(COMPAT)
    required = (
        PINNED,
        "navigator.findPath(",
        "navigator.getCostForPath(",
        'foreach (name in ["First", "SecondLastBeforeEnd", "LastBeforeEnd", "End"])',
        "affordances._nativeCostAnchors <- function(_costs)",
        "affordances._nativeCostAnchorPath <- function(",
        "local anchors = this._nativeCostAnchors(_costs);",
        "foreach (tile in anchors)",
        "this._canonicalNeighbors(_projection, lastTileId, tileId)",
        "path.push(tile);",
        "path.len() != _costs.Tiles",
        "native movement anchor count differs from native tile count",
    )
    for token in required:
        assert token in text

    assert "for (local apBudget" not in text
    assert "_navigator.getCostForPath(" not in text


def test_anchor_gaps_and_count_mismatches_fail_closed() -> None:
    text = _text(COMPAT)
    for token in (
        "native movement path leaves the player-legal canonical map",
        "native movement cost anchors left a canonical path gap",
        "native movement anchor count differs from native tile count",
        "reconstructed native movement path does not terminate at destination",
    ):
        assert token in text


def test_complete_paths_only() -> None:
    text = _text(COMPAT)
    for token in (
        '"IsComplete" in costs',
        "costs.Tiles != 0 && costs.IsComplete",
        "!found || costs == null || costs.Tiles == 0 || !complete",
        "legal.tileID(_costs.End) != destinationId",
    ):
        assert token in text


def test_read_only_path_api() -> None:
    text = _text(COMPAT)
    for token in (
        ".getPath(",
        ".Path",
        ".m.Path",
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
        "DEBUG_GROUND_TRUTH",
        "omniscient_debug",
    ):
        assert token not in text


def test_move_override_preserves_costs_path_and_reactions() -> None:
    text = _text(COMPAT)
    for token in (
        "affordances._moveActions = function(_raw, _projection)",
        "settings.ZoneOfControlCost = 0;",
        'this._movementCost(costs, "ActionPointsRequired", "ActionPoints")',
        'this._movementCost(costs, "FatigueRequired", "Fatigue")',
        "action.destination_tile_id = legal.tileID(destination);",
        "action.resolved_path.push(legal.tileID(tile))",
        "this._aooReactions(",
        "this._resolvedCosts(action, apCost, fatigueCost);",
    ):
        assert token in text
