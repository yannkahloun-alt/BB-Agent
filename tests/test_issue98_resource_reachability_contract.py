from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "companion_mod/scripts/bb_agent/runtime_movement_graph_compat.nut"


def _text() -> str:
    return GRAPH.read_text(encoding="utf-8")


def test_player_legal_graph_integrates_resource_reachability() -> None:
    text = _text()
    assert "affordances._movementReachability <- function(_raw, _projection)" in text
    assert "labels_by_tile" in text
    assert "ap_left" in text
    assert "fatigue" in text
    assert "_movementLabelDominates" in text


def test_move_actions_use_feasible_reachability_not_posthoc_path_filter() -> None:
    text = _text()
    move = text[text.index("affordances._moveActions = function") :]
    assert "local tree = this._movementReachability(_raw, _projection);" in move
    assert "_movementPathAffordability" not in move
    assert "node.ap_spent" in move
    assert "node.fatigue_spent" in move


def test_reachability_rounds_resources_after_every_step() -> None:
    text = _text()
    reachability = text[
        text.index("affordances._movementReachability <- function") : text.index(
            "affordances._moveActions = function"
        )
    ]
    assert "::Math.round(current.ap_left - step.ap)" in reachability
    assert "::Math.round(current.fatigue + step.execution_fatigue)" in reachability
    assert "active.getFatigueMax()" in reachability


def test_unresolved_jump_edges_stay_out_of_resource_search() -> None:
    text = _text()
    assert "if (!transition.resource_cost_resolved)" in text
    assert "unresolved_jump_edges" in text
