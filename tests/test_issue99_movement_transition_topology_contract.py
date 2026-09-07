from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
BASE = ROOT / "companion_mod/scripts/bb_agent/runtime_navigator_path_compat.nut"
GRAPH = ROOT / "companion_mod/scripts/bb_agent/runtime_movement_graph_compat.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_issue98_graph_layer_replaces_smoke_tiebreak_overrides() -> None:
    preload = _text(PRELOAD)
    base = "scripts/bb_agent/runtime_navigator_path_compat"
    graph = "scripts/bb_agent/runtime_movement_graph_compat"
    compare = "scripts/bb_agent/runtime_debug_oracle_movement_compare"

    assert graph in preload
    assert preload.index(base) < preload.index(graph) < preload.index(compare)
    assert "runtime_navigator_tiebreak_compat" not in preload
    assert "runtime_debug_oracle_tiebreak_samples" not in preload


def test_visible_actor_occupancy_is_relation_aware_and_projection_only() -> None:
    text = _text(GRAPH)

    for token in (
        "affordances._movementVisibleOccupancy <- function(_projection)",
        'actor.position.representation != "EXACT"',
        'actor.relation == "HOSTILE"',
        'actor.relation == "ALLY"',
        'actor.relation == "PLAYER"',
        'ret[actor.position.value] <- kind;',
    ):
        assert token in text

    for forbidden in (
        "getAllInstances",
        "isHiddenToPlayer",
        ".getEntity()",
        "tile.IsEmpty",
    ):
        assert forbidden not in text


def test_transition_generator_supports_exactly_one_allied_jump() -> None:
    text = _text(GRAPH)

    for token in (
        "affordances._movementTransitionsFrom <- function(",
        "local neighborId = record.neighbor_ids[direction];",
        'if (occupantKind == "ALLY")',
        "local allyRecord = _projection.runtime.tile_records[neighborId];",
        "local landingId = allyRecord.neighbor_ids[direction];",
        "if (landingId in _occupancy) continue;",
        'kind = "ALLY_JUMP"',
        "via_tile_id = neighborId",
        "landing_tile_id = landingId",
    ):
        assert token in text

    # A jump must land before another jump; the pass-over ally is never expanded
    # recursively as a landed movement state.
    jump = text[text.index('if (occupantKind == "ALLY")') :]
    assert "_movementTransitionsFrom(_raw, _projection, neighborId" not in jump


def test_enemy_occupied_neighbor_is_neither_landing_nor_jump() -> None:
    text = _text(GRAPH)
    assert 'if (occupantKind == "HOSTILE") continue;' in text


def test_ordinary_empty_neighbor_remains_a_direct_transition() -> None:
    text = _text(GRAPH)
    for token in (
        'kind = "STEP"',
        "via_tile_id = null",
        "landing_tile_id = neighborId",
    ):
        assert token in text


def test_zoc_path_penalty_is_attached_to_exit_edge() -> None:
    text = _text(GRAPH)
    for token in (
        "affordances._movementZocExitPenalty <- function(_zocCounts, _fromTileId)",
        "return _fromTileId in _zocCounts ? 4 : 0;",
        "this._movementZocExitPenalty(zocCounts, currentId)",
    ):
        assert token in text

    assert "this._movementVisibleZocPenalty(zocCounts, neighborId)" not in text


def test_graph_expansion_keeps_source_proven_step_legality() -> None:
    base = _text(BASE)
    graph = _text(GRAPH)

    for token in (
        "::Const.Tactical.TerrainType.Impassable",
        "::Math.abs(levelDifference) > _active.getMaxTraversibleLevels()",
    ):
        assert token in base

    # Every legal landing still goes through the source-derived terrain/elevation
    # step-cost helper. Ally-jump resource charging itself remains deliberately
    # unresolved in issue #98 and is not asserted here.
    assert "this._movementStepCosts(" in graph


def test_graph_production_still_has_zero_native_pathfinder_calls() -> None:
    text = _text(GRAPH)
    for forbidden in (
        "navigator.findPath(",
        "navigator.getCostForPath(",
        "buildVisualisation(",
        "Math.rand(",
        "::Math.rand(",
        "omniscient_debug",
        "DEBUG_GROUND_TRUTH",
    ):
        assert forbidden not in text
