from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
FASTPATH = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_player_legal_turn_list_fastpath.nut"
)


def test_turn_list_fastpath_loads_after_actor_enumeration_compat() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    enumeration = preload.index("runtime_player_legal_actor_enumeration_compat")
    fastpath = preload.index("runtime_player_legal_turn_list_fastpath")
    identity = preload.index("canonical_identity")
    assert enumeration < fastpath < identity


def test_turn_list_fastpath_removes_native_entity_manager_scan() -> None:
    text = FASTPATH.read_text(encoding="utf-8")
    assert "TurnSequenceBar.getCurrentEntities()" in text
    assert "local raw = clone _raw;" in text
    assert "raw.EntityManager = {" in text
    assert "return [current];" in text
    assert "native_entity_manager_scan=false" in text
    assert "_raw.EntityManager.getAllInstances()" not in text
