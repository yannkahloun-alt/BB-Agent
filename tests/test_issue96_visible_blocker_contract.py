from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOCKING = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_player_legal_blocking_compat.nut"
)
MOVEMENT_BLOCKING = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_movement_blocking_compat.nut"
)
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"


def test_visible_tiles_export_player_legal_blocking_without_remembering_dynamic_blockers() -> (
    None
):
    text = BLOCKING.read_text(encoding="utf-8")
    assert "legal._visibleTileBlocking <- function(_tile)" in text
    assert "tile.blocking = wire.exactObserved(_record.blocking);" in text
    assert "tile.blocking = wire.unknownValue();" in text


def test_hidden_actor_does_not_become_player_known_blocker() -> None:
    text = BLOCKING.read_text(encoding="utf-8")
    helper = text[
        text.index("legal._visibleTileBlocking") : text.index(
            "local originalVisibleTileRecord"
        )
    ]
    assert '"isPlayerControlled" in entity' in helper
    assert "entity.isHiddenToPlayer()" in helper
    assert "return false;" in helper


def test_movement_occupancy_includes_visible_blocker_class_without_raw_tile_reads() -> (
    None
):
    text = MOVEMENT_BLOCKING.read_text(encoding="utf-8")
    assert 'tile.blocking.representation != "EXACT"' in text
    assert "tile.blocking.value" in text
    assert 'ret[tile.tile_id] <- "BLOCKED";' in text
    assert 'kind == "BLOCKED"' in text
    for forbidden in ("tile.IsEmpty", ".getEntity()", "isHiddenToPlayer"):
        assert forbidden not in text


def test_blocking_layers_load_before_sandbox_and_after_base_graph() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    projection = preload.index("scripts/bb_agent/runtime_player_legal_blocking_compat")
    graph = preload.index("scripts/bb_agent/runtime_movement_graph_compat")
    movement = preload.index("scripts/bb_agent/runtime_movement_blocking_compat")
    sandbox = preload.index("scripts/bb_agent/runtime_combat_sandbox")
    assert projection < graph < movement < sandbox
