from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "companion_mod/scripts/bb_agent/runtime_movement_graph_compat.nut"
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
DOC = ROOT / "docs/PLAYER_LEGAL_MOVEMENT.md"


def test_production_graph_does_not_inspect_raw_hidden_occupancy() -> None:
    text = GRAPH.read_text(encoding="utf-8")
    for forbidden in (
        "tile.IsEmpty",
        "destination.IsEmpty",
        ".getEntity()",
        "isHiddenToPlayer",
        "getAllInstances",
    ):
        assert forbidden not in text


def test_hidden_inspecting_blocker_compatibility_layers_are_not_loaded() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    assert "runtime_player_legal_blocking_compat" not in preload
    assert "runtime_movement_blocking_compat" not in preload


def test_visible_non_actor_blocker_acquisition_is_explicitly_unresolved() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "Visible non-actor blocker acquisition is still unresolved" in text
    assert "must not be inferred from raw `Tile.IsEmpty`" in text
