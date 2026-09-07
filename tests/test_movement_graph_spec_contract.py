from pathlib import Path


RUNTIME = Path("companion_mod/scripts/bb_agent/runtime_navigator_path_compat.nut")


def _source() -> str:
    return RUNTIME.read_text(encoding="utf-8")


def test_friendly_occupancy_is_not_a_universal_blocker() -> None:
    source = _source()
    assert "_movementFriendlyJumpLanding" in source
    assert "if (!tile.IsEmpty) blocked[tileId] <- true;" not in source


def test_zoc_penalty_is_charged_on_exit_not_entry() -> None:
    source = _source()
    assert "_movementVisibleZocExitPenalty" in source
    assert "_movementVisibleZocPenalty(zocCounts, neighborId)" not in source


def test_resource_reachability_is_integrated_into_graph_search() -> None:
    source = _source()
    assert "_movementReachability" in source
    assert "_movementPathAffordability(active, pathTiles)" not in source


def test_player_legal_graph_has_no_native_pathfinder_dependency() -> None:
    source = _source()
    assert ".findPath(" not in source
    assert "Tactical.getNavigator" not in source
