from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_smoke_tiebreak_experiment_is_not_loaded_in_topology_phase() -> None:
    preload = _text(PRELOAD)
    assert "scripts/bb_agent/runtime_navigator_tiebreak_compat" not in preload
    assert "scripts/bb_agent/runtime_debug_oracle_tiebreak_samples" not in preload


def test_issue98_defers_native_path_preference_until_graph_is_proven() -> None:
    preload = _text(PRELOAD)
    assert "scripts/bb_agent/runtime_movement_graph_compat" in preload
