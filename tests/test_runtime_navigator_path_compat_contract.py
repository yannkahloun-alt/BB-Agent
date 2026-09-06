from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
COMPAT = ROOT / "companion_mod/scripts/bb_agent/runtime_navigator_path_compat.nut"
PINNED_SOURCE = "162f498ac7c49b4c317bbf54718a595ecef6a65a"


def test_navigator_compat_loads_after_affordance_hardening_before_export() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    hardening = preload.index('::include("scripts/bb_agent/affordance_export_hardening")')
    compat = preload.index('::include("scripts/bb_agent/runtime_navigator_path_compat")')
    export = preload.index('::include("scripts/bb_agent/live_export")')
    assert hardening < compat < export


def test_navigator_compat_uses_pinned_cost_prefix_oracle() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    assert PINNED_SOURCE in text
    for required in (
        "navigator.findPath(",
        "_navigator.getCostForPath(",
        '"IsComplete" in _costs',
        '"End" in _costs',
        '"Tiles" in _costs',
        "for (local apBudget = 1; apBudget <= apRequired;",
        "prefix.Tiles != observedTiles + 1",
        "path.push(prefix.End);",
    ):
        assert required in text


def test_navigator_compat_exports_only_complete_affordable_paths() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    assert '"IsComplete" in costs' in text
    assert "costs.Tiles != 0 && costs.IsComplete" in text
    assert "!found || costs == null || costs.Tiles == 0 || !complete" in text
    assert "legal.tileID(_costs.End) != legal.tileID(_destination)" in text
    assert "observedTiles != _costs.Tiles || path.len() != _costs.Tiles" in text
    assert "native movement path leaves the player-legal canonical map" in text


def test_navigator_compat_does_not_use_unsupported_or_executing_path_apis() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    for forbidden in (
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
    ):
        assert forbidden not in text


def test_active_move_override_preserves_native_costs_path_and_reactions() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    assert "affordances._moveActions = function(_raw, _projection)" in text
    assert "settings.ZoneOfControlCost = 0;" in text
    assert 'this._movementCost(costs, "ActionPointsRequired", "ActionPoints")' in text
    assert 'this._movementCost(costs, "FatigueRequired", "Fatigue")' in text
    assert "action.destination_tile_id = legal.tileID(destination);" in text
    assert "action.resolved_path.push(legal.tileID(tile))" in text
    assert "this._aooReactions(" in text
    assert "this._resolvedCosts(action, apCost, fatigueCost);" in text
    assert "this._navigatorPath(" not in text
