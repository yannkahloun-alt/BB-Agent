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
    graph = "scripts/bb_agent/runtime_movement_graph_compat"
    compare = "scripts/bb_agent/runtime_debug_oracle_movement_compare"
    export = "scripts/bb_agent/live_export"
    assert (
        preload.index(hardening)
        < preload.index(oracle)
        < preload.index(compat)
        < preload.index(graph)
        < preload.index(compare)
        < preload.index(export)
    )


def test_source_aligned_tree_selects_path_before_affordability() -> None:
    text = _text(COMPAT)
    for token in (
        PINNED,
        "affordances._movementTree <- function(_raw, _projection)",
        "affordances._movementPathAffordability <- function(_active, _pathTiles)",
        "local tree = this._movementTree(_raw, _projection);",
        "local affordability = this._movementPathAffordability(active, pathTiles);",
        "if (!affordability.affordable) continue;",
    ):
        assert token in text

    tree = text[
        text.index("affordances._movementTree <- function") : text.index(
            "affordances._movementPathFromTree <- function"
        )
    ]
    assert "getActionPoints()" not in tree
    assert "getFatigueMax()" not in tree
    assert "getFatigue()" not in tree
    assert "remainingAP" not in tree


def test_search_and_execution_use_distinct_fatigue_costs() -> None:
    text = _text(COMPAT)
    for token in (
        "path_fatigue = pathFatigue",
        "execution_fatigue = pathFatigue * fatigueEffectMult",
        "step.path_fatigue * ::Const.Movement.FatigueCostFactor",
        "fatigue + step.execution_fatigue > fatigueMax",
        "::Math.round(fatigue + step.execution_fatigue)",
    ):
        assert token in text

    score = text[
        text.index("local score = current.score") : text.index(
            "local depth = current.depth + 1;"
        )
    ]
    assert "execution_fatigue" not in score
    assert "FatigueEffectMult" not in score


def test_actor_step_rounding_occurs_after_each_selected_step() -> None:
    text = _text(COMPAT)
    affordability = text[
        text.index("affordances._movementPathAffordability") : text.index(
            "// Replace movement enumeration only"
        )
    ]
    for token in (
        "if (ap < step.ap || fatigue + step.execution_fatigue > fatigueMax)",
        "ap = ::Math.round(ap - step.ap);",
        "fatigue = ::Math.min(",
        "::Math.round(fatigue + step.execution_fatigue)",
        "ap = ::Math.round(startAP - ap)",
        "fatigue = ::Math.round(fatigue - startFatigue)",
    ):
        assert token in affordability

    assert "fatigueBudget" not in text
    assert "active actor has invalid fatigue budget" not in text
    assert "active actor has invalid fatigue values" not in text


def test_discovered_destination_gate_remains_separate_from_graph_occupancy() -> None:
    text = _text(COMPAT)
    for token in (
        "affordances._movementExactVisibleTileMap <- function",
        "if (!destination.IsDiscovered) continue;",
        "if (!destination.IsEmpty) continue;",
        "scope=exact_visible discovered_scope_pending=true",
    ):
        assert token in text

    # Issue #98 moves relation-aware traversal into a dedicated graph layer.
    assert "if (!tile.IsEmpty) blocked[tileId] <- true;" not in text


def test_visible_zoc_and_aoo_do_not_use_hidden_global_zone_counts() -> None:
    text = _text(COMPAT)
    for token in (
        "affordances._movementVisibleZocCounts <- function",
        "nativeActor.isExertingZoneOfControl()",
        "nativeActor.hasZoneOfControl()",
        "affordances._movementVisibleAooReactors <- function",
        "_active.getCurrentProperties().IsImmuneToZoneOfControl",
        '_originTile.Properties.Effect.Type == "smoke"',
        "reactor.isExertingZoneOfControl()",
        "reactor.hasZoneOfControl()",
    ):
        assert token in text
    assert "getZoneOfControlCountOtherThan" not in text


def test_player_legal_producer_has_zero_native_pathfinder_calls() -> None:
    text = _text(COMPAT)
    assert "navigator.findPath(" not in text
    assert "navigator.getCostForPath(" not in text
    assert "_navigator.getCostForPath(" not in text
    assert "native_find_path_calls=0" in text


def test_movement_tree_rejects_unsupported_or_impossible_steps() -> None:
    text = _text(COMPAT)
    for token in (
        "::Const.Tactical.TerrainType.Impassable",
        "visible movement tile has unsupported terrain cost index",
        "::Math.abs(levelDifference) > _active.getMaxTraversibleLevels()",
        "owned actor movement rule produced an invalid AP step cost",
        "owned actor movement rule produced unsupported negative path fatigue",
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
        "omniscient_debug",
        "DEBUG_GROUND_TRUTH",
        "BBAGENT_DEBUG_ORACLE",
        "getAllInstances",
        "isHiddenToPlayer",
    ):
        assert forbidden not in text


def test_move_override_preserves_paths_costs_and_reactions() -> None:
    text = _text(COMPAT)
    for token in (
        "affordances._moveActions = function(_raw, _projection)",
        "local pathTiles = this._movementPathFromTree(",
        "action.destination_tile_id = destinationId;",
        "action.resolved_path.push(legal.tileID(tile))",
        "this._aooReactions(",
        "this._resolvedCosts(action, affordability.ap, affordability.fatigue);",
    ):
        assert token in text
