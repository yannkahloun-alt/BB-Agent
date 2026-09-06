from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
COMPAT = ROOT / "companion_mod/scripts/bb_agent/runtime_entity_fingerprint_compat.nut"


def test_entity_fingerprint_compat_loads_before_tactical_hook() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    sha_compat = preload.index('::include("scripts/bb_agent/runtime_sha256_compat")')
    entity_compat = preload.index(
        '::include("scripts/bb_agent/runtime_entity_fingerprint_compat")'
    )
    hook = preload.index('::include("scripts/bb_agent/hooks/tactical_state")')
    assert sha_compat < entity_compat < hook


def test_entity_fingerprint_compat_uses_actor_null_guard_only() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    assert "capture._entityTokens = function()" in text
    assert "capture._turnSequenceTokens = function()" in text
    assert "local groups = ::Tactical.Entities.getAllInstances();" in text
    assert "local entities = ::Tactical.TurnSequenceBar.getCurrentEntities();" in text
    assert text.count("if (actor == null) continue;") == 2
    assert ".isNull(" not in text


def test_entity_fingerprint_compat_preserves_token_construction() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    assert "ret.push(this._actorToken(actor));" in text
    assert "ret.sort();" in text
    assert 'ret.push("turn=" + index + ":" + actor.getID());' in text


def test_entity_fingerprint_compat_preserves_safety_boundary() -> None:
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
