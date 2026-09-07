from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTION = ROOT / "companion_mod/scripts/bb_agent/player_legal_projection.nut"
GRAPH = ROOT / "companion_mod/scripts/bb_agent/runtime_movement_graph_compat.nut"


def test_visible_tiles_export_player_legal_blocking_without_remembering_dynamic_blockers() -> None:
    text = PROJECTION.read_text(encoding="utf-8")
    assert "function _visibleTileBlocking(_tile, _visibleActorByTile)" in text
    assert "blocking = wire.exactObserved(_record.blocking)" in text
    assert "blocking = wire.unknownValue()" in text


def test_hidden_actor_does_not_become_player_known_blocker() -> None:
    text = PROJECTION.read_text(encoding="utf-8")
    helper = text[
        text.index("function _visibleTileBlocking") : text.index(
            "function _visibleTileRecord"
        )
    ]
    assert "_visibleActorByTile" in helper
    assert '"isPlayerControlled" in entity' in helper
    assert "return false;" in helper


def test_movement_occupancy_includes_visible_blocker_class_without_raw_tile_reads() -> None:
    text = GRAPH.read_text(encoding="utf-8")
    assert 'tile.blocking.representation == "EXACT"' in text
    assert "tile.blocking.value" in text
    assert 'ret[tile.tile_id] <- "BLOCKED";' in text
    assert 'occupantKind == "HOSTILE" || occupantKind == "BLOCKED"' in text
    for forbidden in ("tile.IsEmpty", ".getEntity()", "isHiddenToPlayer"):
        assert forbidden not in text
