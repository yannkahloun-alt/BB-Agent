from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
COMPAT = ROOT / "companion_mod/scripts/bb_agent/runtime_player_legal_actor_compat.nut"


def test_player_legal_actor_compat_loads_after_hardening_before_identity() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    hardening = preload.index('::include("scripts/bb_agent/player_legal_hardening")')
    compat = preload.index(
        '::include("scripts/bb_agent/runtime_player_legal_actor_compat")'
    )
    identity = preload.index('::include("scripts/bb_agent/canonical_identity")')
    assert hardening < compat < identity


def test_player_legal_actor_compat_removes_active_isnull_dependency() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    assert "legal.build = function(_raw)" in text
    assert 'if (actor == null || !("isPlayerControlled" in actor)) continue;' in text
    assert "if (actor == null) continue;" in text
    assert ".isNull(" not in text


def test_player_legal_actor_compat_preserves_visibility_and_turn_compaction() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    for required in (
        "if (!this._visibleToPlayer(actor)) continue;",
        "local projected = this._visibleActor(_raw, active, actor);",
        "actorByRuntimeID[actor.getID().tostring()] <- projected.actor_id;",
        'if (key.find("actor-memory:") != 0) continue;',
        'if (key.find("tile-memory:") != 0) continue;',
        "local maximum = _raw.TurnSequenceBar.m.MaxVisibleEntities;",
        "sequence = wire.exactObserved(turnEntries.len())",
        "if (turnEntries.len() >= maximum) break;",
        'information_profile = "player_legal"',
    ):
        assert required in text


def test_player_legal_actor_compat_preserves_safety_boundary() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    for forbidden in (
        "Math.rand(",
        "::Math.rand(",
        ".payForAction(",
        ".equip(",
        ".unequip(",
        ".swap(",
        ".use(",
        ".wait(",
        ".endTurn(",
        "getNavigator().travel(",
        "DEBUG_GROUND_TRUTH",
        "DEBUG_ORACLE",
        "omniscient_debug",
    ):
        assert forbidden not in text
