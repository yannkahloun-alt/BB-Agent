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
    compat = "scripts/bb_agent/runtime_navigator_path_compat"
    export = "scripts/bb_agent/live_export"
    assert preload.index(hardening) < preload.index(compat) < preload.index(export)


def test_native_prefix_oracle() -> None:
    text = _text(COMPAT)
    required = (
        PINNED,
        "navigator.findPath(",
        "_navigator.getCostForPath(",
        '"IsComplete" in _costs',
        '"End" in _costs',
        '"Tiles" in _costs',
        "for (local apBudget = 1; apBudget <= apRequired;",
        "prefix.Tiles != observedTiles + 1",
        "path.push(prefix.End);",
    )
    for token in required:
        assert token in text


def test_complete_paths_only() -> None:
    text = _text(COMPAT)
    required = (
        '"IsComplete" in costs',
        "costs.Tiles != 0 && costs.IsComplete",
        "!found || costs == null || costs.Tiles == 0 || !complete",
        "legal.tileID(_costs.End) != legal.tileID(_destination)",
        "observedTiles != _costs.Tiles || path.len() != _costs.Tiles",
        "native movement path leaves the player-legal canonical map",
    )
    for token in required:
        assert token in text


def test_read_only_path_api() -> None:
    text = _text(COMPAT)
    forbidden = (
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
        "DEBUG_ORACLE",
        "omniscient_debug",
    )
    for token in forbidden:
        assert token not in text


def test_move_override_preserves_costs_path_and_reactions() -> None:
    text = _text(COMPAT)
    required = (
        "affordances._moveActions = function(_raw, _projection)",
        "settings.ZoneOfControlCost = 0;",
        'this._movementCost(costs, "ActionPointsRequired", "ActionPoints")',
        'this._movementCost(costs, "FatigueRequired", "Fatigue")',
        "action.destination_tile_id = legal.tileID(destination);",
        "action.resolved_path.push(legal.tileID(tile))",
        "this._aooReactions(",
        "this._resolvedCosts(action, apCost, fatigueCost);",
    )
    for token in required:
        assert token in text
    assert "this._navigatorPath(" not in text
