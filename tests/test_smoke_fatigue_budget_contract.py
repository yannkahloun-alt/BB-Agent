from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPAT = ROOT / "companion_mod/scripts/bb_agent/runtime_navigator_path_compat.nut"


def test_over_cap_fatigue_is_not_a_capture_fault() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    assert "local fatigueBudget" not in text
    assert "active actor has invalid fatigue budget" not in text
    assert "active actor has invalid fatigue values" not in text
    assert "local fatigue = startFatigue;" in text
    assert "fatigue + step.execution_fatigue > fatigueMax" in text
    assert "::Math.round(fatigue + step.execution_fatigue)" in text
    assert "native_find_path_calls=0" in text
