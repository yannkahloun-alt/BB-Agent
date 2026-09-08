from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPAT = ROOT / "companion_mod/scripts/bb_agent/runtime_navigator_path_compat.nut"


def test_live_movement_performance_regression_stays_removed() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    assert "movement_tree reachable=" in text
    assert "native_find_path_calls=0" in text
    assert "navigator.findPath(" not in text
    assert "navigator.getCostForPath(" not in text
    assert "_navigator.getCostForPath(" not in text
    assert "_movementCandidateTileIds" not in text
    assert "movement_candidate_bound" not in text
