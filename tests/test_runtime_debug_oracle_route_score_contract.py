from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
TRACE = ROOT / "companion_mod/scripts/bb_agent/runtime_debug_oracle_route_score.nut"
COMPAT = ROOT / "companion_mod/scripts/bb_agent/runtime_navigator_path_compat.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_route_score_diagnostics_load_after_comparator_before_sample_override() -> None:
    preload = _text(PRELOAD)
    compare = preload.index("scripts/bb_agent/runtime_debug_oracle_movement_compare")
    trace = preload.index("scripts/bb_agent/runtime_debug_oracle_route_score")
    samples = preload.index("scripts/bb_agent/runtime_debug_oracle_tiebreak_samples")
    assert compare < trace < samples


def test_route_score_diagnostics_reuse_production_cost_model_without_native_calls() -> None:
    trace = _text(TRACE)
    compat = _text(COMPAT)
    assert "affordances._movementStepCosts(" in trace
    assert "affordances._movementVisibleZocPenalty(" in trace
    assert "movement_compare_route_step" in trace
    assert "movement_compare_route_summary" in trace
    assert "navigator.findPath(" not in trace
    assert "navigator.getCostForPath(" not in trace
    assert "native_find_path_calls=0" in compat
