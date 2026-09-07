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


def test_player_legal_movement_tree_replaces_per_destination_native_pathfinding() -> None:
    text = _text(COMPAT)
    for token in (
        PINNED,
        "affordances._movementVisibleTileMap <- function",
        "affordances._movementVisibleBlockedTiles <- function",
        "affordances._movementStepCosts <- function(",
        "affordances._movementTree <- function(_raw, _projection)",
        "affordances._movementPathFromTree <- function(",
        "record.neighbor_ids",
        "active.getActionPointCosts()",
        "active.getFatigueCosts()",
        "active.getLevelActionPointCost()",
        "active.getLevelFatigueCost()",
        "active.getMaxTraversibleLevels()",
        "FatigueEffectMult",
        "::Const.Movement.LevelClimbingFatigueCost",
        "::Const.Movement.FatigueCostFactor",
        "movement_tree reachable=",
        "native_find_path_calls=0",
    ):
        assert token in text

    assert "navigator.findPath(" not in text
    assert "navigator.getCostForPath(" not in text
    assert "_navigator.getCostForPath(" not in text


def test_movement_tree_is_player_legal_and_affordability_bounded() -> None:
    text = _text(COMPAT)
    for token in (
        "this._visibleTargetTiles(_projection)",
        "_projection.runtime.tile_records",
        "_projection.state.combatants",
        'actor.position.representation != "EXACT"',
        'actor.visible',
        "properties.IsRooted || properties.IsStunned",
        "remainingAP < step.ap",
        "currentFatigue + step.fatigue > fatigueMax",
        "::Math.round(remainingAP - step.ap)",
        "::Math.round(currentFatigue + step.fatigue)",
        "this._canonicalNeighbors(_projection, currentId, neighborId)",
        "this._movementVisibleZocPenalty(_projection, active, nextTile)",
    ):
        assert token in text

    for forbidden in (
        "omniscient_debug",
        "DEBUG_GROUND_TRUTH",
        "BBAGENT_DEBUG_ORACLE",
        "getAllInstances",
        "isHiddenToPlayer",
    ):
        assert forbidden not in text


def test_over_cap_fatigue_is_zero_available_budget_not_capture_failure() -> None:
    text = _text(COMPAT)
    assert "local fatigueBudget = ::Math.max(0, fatigueMax - fatigueStart);" in text
    assert "fatigueBudget < 0" not in text
    assert "active actor has invalid fatigue budget" not in text
    assert "active actor has invalid fatigue values" in text
    assert '" fatigue=" + fatigueStart + "/" + fatigueMax' in text


def test_movement_tree_rejects_unsupported_or_impossible_steps() -> None:
    text = _text(COMPAT)
    for token in (
        "::Const.Tactical.TerrainType.Impassable",
        "visible movement tile has unsupported terrain cost index",
        "::Math.abs(levelDifference) > _active.getMaxTraversibleLevels()",
        "owned actor movement rule produced an invalid step cost",
        "movement tree reached a tile outside canonical records",
        "movement tree encountered inconsistent canonical adjacency",
        "movement tree predecessor chain is invalid",
        "movement tree path is not canonically adjacent",
        "movement tree path does not terminate at destination",
    ):
        assert token in text


def test_read_only_movement_enumerator_never_executes_commands() -> None:
    text = _text(COMPAT)
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
        assert forbidden not in text


def test_move_override_preserves_paths_costs_and_reactions() -> None:
    text = _text(COMPAT)
    for token in (
        "affordances._moveActions = function(_raw, _projection)",
        "local tree = this._movementTree(_raw, _projection);",
        "local pathTiles = this._movementPathFromTree(",
        "action.destination_tile_id = destinationId;",
        "action.resolved_path.push(legal.tileID(tile))",
        "this._aooReactions(",
        "this._resolvedCosts(action, node.ap, node.fatigue);",
    ):
        assert token in text
