from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
NUMERIC = ROOT / "companion_mod/scripts/bb_agent/runtime_player_legal_numeric_compat.nut"
PROJECTION = ROOT / "companion_mod/scripts/bb_agent/player_legal_projection.nut"


def test_numeric_layer_order() -> None:
    text = PRELOAD.read_text(encoding="utf-8")
    hardening = text.index("player_legal_hardening")
    numeric = text.index("runtime_player_legal_numeric_compat")
    blocker = text.index("runtime_player_legal_blocking_compat")
    assert hardening < numeric < blocker


def test_whole_number_normalization_contract() -> None:
    text = NUMERIC.read_text(encoding="utf-8")
    assert "value.tointeger()" in text
    assert "if (value != integerValue)" in text
    assert "whole-number field is fractional" in text
    assert "equipment.condition" in text
    assert "equipment.ammunition" in text
    assert "tactical_stats." in text


def test_live_source_getters_remain_authoritative() -> None:
    text = PROJECTION.read_text(encoding="utf-8")
    assert "condition = wire.exactObserved(_item.getCondition())" in text
    assert "maximum_hit_points" in text
    assert "getHitpointsMax()" in text
    assert "getInitiative()" in text
    assert "getMeleeSkill()" in text
    assert "getRangedSkill()" in text
