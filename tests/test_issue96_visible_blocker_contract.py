from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "companion_mod/scripts/bb_agent/runtime_movement_graph_compat.nut"
BLOCKING = ROOT / "companion_mod/scripts/bb_agent/runtime_player_legal_blocking_compat.nut"
MOVEMENT_BLOCKING = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_movement_blocking_compat.nut"
)
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"


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


def test_visible_tile_blocking_uses_only_visible_tile_is_empty_state() -> None:
    text = BLOCKING.read_text(encoding="utf-8")
    assert "record.blocking <- !_tile.IsEmpty;" in text
    assert "tile.blocking = wire.exactObserved(_record.blocking);" in text
    assert "tile.blocking = wire.unknownValue();" in text
    for forbidden in ("getEntity(", "isHiddenToPlayer", "getAllInstances"):
        assert forbidden not in text


def test_movement_graph_consumes_only_projected_blocker_state() -> None:
    text = MOVEMENT_BLOCKING.read_text(encoding="utf-8")
    assert 'tile.blocking.representation != "EXACT"' in text
    assert "tile.blocking.value" in text
    assert 'ret[tile.tile_id] <- "BLOCKED";' in text
    assert 'if (kind == "BLOCKED") continue;' in text
    for forbidden in ("IsEmpty", "getEntity(", "isHiddenToPlayer", "getAllInstances"):
        assert forbidden not in text


def test_actor_relations_override_generic_visible_blocker_class() -> None:
    text = MOVEMENT_BLOCKING.read_text(encoding="utf-8")
    assert "local actorOccupancy = baseVisibleOccupancy.acall([this, _projection]);" in text
    assert "ret[tileId] <- kind;" in text


def test_safe_blocking_layers_are_loaded_around_base_graph() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    projection = preload.index("scripts/bb_agent/runtime_player_legal_blocking_compat")
    graph = preload.index("scripts/bb_agent/runtime_movement_graph_compat")
    movement = preload.index("scripts/bb_agent/runtime_movement_blocking_compat")
    sandbox = preload.index("scripts/bb_agent/runtime_combat_sandbox")
    assert projection < graph < movement < sandbox
