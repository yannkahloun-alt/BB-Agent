from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
FALLBACK = (
    ROOT
    / "companion_mod/scripts/bb_agent/runtime_player_legal_actor_enumeration_compat.nut"
)


def test_actor_enumeration_fallback_loads_after_actor_compat() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    base = preload.index("scripts/bb_agent/runtime_player_legal_actor_compat")
    fallback = preload.index(
        "scripts/bb_agent/runtime_player_legal_actor_enumeration_compat"
    )
    identity = preload.index("scripts/bb_agent/canonical_identity")
    assert base < fallback < identity


def test_fallback_repairs_zero_combatant_projection() -> None:
    text = FALLBACK.read_text(encoding="utf-8")
    assert "projection.state.combatants.len() != 0" in text
    assert "_raw.TurnSequenceBar.getCurrentEntities()" in text
    assert "actor.isPlayerControlled();" in text
    assert "actor.isAlive();" in text
    assert "actor.isPlacedOnMap();" in text
    assert '"isPlayerControlled" in actor' not in text
    assert "this._visibleToPlayer(actor)" in text
    assert "this._visibleActor(_raw, active, actor)" in text


def test_fallback_repairs_actor_dependent_player_legal_views() -> None:
    text = FALLBACK.read_text(encoding="utf-8")
    for required in (
        "projection.state.combatants = actors;",
        "projection.state.battle.hostile_faction_ids = hostile;",
        "projection.state.battle.allied_faction_ids = allied;",
        "projection.state.turn_state.entries = turnEntries;",
        "projection.runtime.actor_by_runtime_id = actorByRuntimeID;",
        "tile.occupant_actor_id = tile.tile_id in actorByTile",
    ):
        assert required in text
