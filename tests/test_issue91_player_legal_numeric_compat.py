from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
NUMERIC = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_player_legal_numeric_compat.nut"
)
PROJECTION = ROOT / "companion_mod/scripts/bb_agent/player_legal_projection.nut"


def test_numeric_compat_loads_after_projection_before_projection_consumers() -> (
    None
):
    preload = PRELOAD.read_text(encoding="utf-8")
    projection = preload.index("player_legal_hardening")
    numeric = preload.index("runtime_player_legal_numeric_compat")
    blocker = preload.index("runtime_player_legal_blocking_compat")
    assert projection < numeric < blocker


def test_numeric_compat_normalizes_live_whole_number_getters_fail_closed() -> (
    None
):
    text = NUMERIC.read_text(encoding="utf-8")
    assert "value.tointeger()" in text
    assert "if (value != integerValue)" in text
    assert "player-legal whole-number field is fractional" in text
    assert "equipment.condition" in text
    for field in (
        "maximum_hit_points",
        "maximum_action_points",
        "fatigue_capacity",
        "head_armor",
        "maximum_head_armor",
        "body_armor",
        "maximum_body_armor",
        "initiative",
    ):
        assert f'"{field}"' in text
    assert "tactical_stats." in text


def test_projection_still_uses_source_getters_and_wire_rejects_generic_floats() -> (
    None
):
    projection = PROJECTION.read_text(encoding="utf-8")
    assert "condition = wire.exactObserved(_item.getCondition())" in projection
    assert (
        "maximum_hit_points = wire.exactObserved(_actor.getHitpointsMax())"
        in projection
    )
    assert "initiative = wire.exactObserved(_actor.getInitiative())" in projection
    assert "getMeleeSkill()" in projection
    assert "getRangedSkill()" in projection
    assert "getMeleeDefense()" in projection
    assert "getRangedDefense()" in projection
