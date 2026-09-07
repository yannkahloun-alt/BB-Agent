from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
TIEBREAK = ROOT / "companion_mod/scripts/bb_agent/runtime_navigator_tiebreak_compat.nut"
SAMPLES = ROOT / "companion_mod/scripts/bb_agent/runtime_debug_oracle_tiebreak_samples.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_tiebreak_compat_loads_between_tree_and_oracle_compare() -> None:
    preload = _text(PRELOAD)
    base = preload.index("scripts/bb_agent/runtime_navigator_path_compat")
    tiebreak = preload.index("scripts/bb_agent/runtime_navigator_tiebreak_compat")
    compare = preload.index("scripts/bb_agent/runtime_debug_oracle_movement_compare")
    samples = preload.index("scripts/bb_agent/runtime_debug_oracle_tiebreak_samples")
    export = preload.index("scripts/bb_agent/live_export")
    assert base < tiebreak < compare < samples < export


def test_equal_score_paths_preserve_native_direction_insertion_order() -> None:
    text = _text(TIEBREAK)
    assert "return _score < _existing.score;" in text
    assert "if (candidate.score < best.score)" in text
    assert "direction < record.neighbor_ids.len()" in text
    assert "local neighborId = record.neighbor_ids[direction];" in text
    assert "candidateId < bestId" not in text
    assert "_previous < _existing.previous" not in text
    assert "tie_policy=native_direction_stable" in text


def test_oracle_uses_one_sanity_and_two_tie_rich_samples() -> None:
    text = _text(SAMPLES)
    assert "local shortest = moves[0];" in text
    assert "action.resolved_path.len() > 4" in text
    assert "while (ret.len() < this.MaxMovementCompareSamples)" in text
    assert "movement_direction_values" in text
