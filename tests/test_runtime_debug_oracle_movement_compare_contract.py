from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
COMPARE = ROOT / "companion_mod/scripts/bb_agent/runtime_debug_oracle_movement_compare.nut"
EXPORT = ROOT / "companion_mod/scripts/bb_agent/live_export.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_general_movement_comparator_is_deferred_from_topology_preload() -> None:
    preload = _text(PRELOAD)
    assert "scripts/bb_agent/runtime_debug_oracle_movement_compare" not in preload
    graph = preload.index("scripts/bb_agent/runtime_movement_graph_compat")
    probe = preload.index("scripts/bb_agent/runtime_debug_oracle_ally_jump_probe")
    export = preload.index("scripts/bb_agent/live_export")
    assert graph < probe < export


def test_deferred_comparator_remains_bounded_if_reenabled_later() -> None:
    compare = _text(COMPARE)
    assert "oracle.MaxMovementCompareSamples <- 3;" in compare
    assert "if (!this.Enabled) return;" in compare
    assert "navigator.findPath(" in compare
    assert "navigator.getCostForPath(" in compare
    assert "movement_compare_begin samples=" in compare
    assert "movement_compare_end samples=" in compare
    assert 'throw "DEBUG_ORACLE movement comparison mismatch";' in compare


def test_comparator_validates_but_never_supplies_player_legal_values() -> None:
    compare = _text(COMPARE)
    export = _text(EXPORT)
    for forbidden in (
        "BBAGENT1|",
        "encodeFrame(",
        "DECISION_ORACLE",
        "record.payload",
        "information_profile",
        "omniscient_debug",
    ):
        assert forbidden not in compare
    assert 'record.information_profile <- "player_legal"' in export


def test_comparator_checks_path_and_native_resolved_costs() -> None:
    compare = _text(COMPARE)
    for token in (
        '["First", "SecondLastBeforeEnd", "LastBeforeEnd", "End"]',
        '"ActionPointsRequired"',
        '"FatigueRequired"',
        "this._movementComparePathsEqual(localPath, nativePath)",
        "nativeAP == _action.ap_cost.value",
        "nativeFatigue == _action.fatigue_cost.value",
        "anchor_coverage=",
        "path_match=",
        "cost_match=",
    ):
        assert token in compare


def test_comparator_logs_all_samples_before_failing_batch() -> None:
    compare = _text(COMPARE)
    assert "local mismatches = 0;" in compare
    assert "++mismatches;" in compare
    assert "if (mismatches != 0)" in compare
    assert compare.index("for (local i = 0; i < samples.len(); i = ++i)") < compare.index(
        "if (mismatches != 0)"
    )


def test_path_mismatch_logs_direction_and_remaining_distance() -> None:
    compare = _text(COMPARE)
    for token in (
        "oracle._movementCompareDivergence <- function(",
        "fromTile.getDirectionTo(localNext)",
        "fromTile.getDirectionTo(nativeNext)",
        "localNext.getDistanceTo(_destination)",
        "nativeNext.getDistanceTo(_destination)",
        "movement_compare_divergence sample=",
    ):
        assert token in compare


def test_sample_selection_is_high_information_and_at_most_three() -> None:
    compare = _text(COMPARE)
    assert "local shortest = moves[0];" in compare
    assert "local longest = null;" in compare
    assert "local zoc = null;" in compare
    assert "action.contingent_reactions.len() != 0" in compare
    assert "ret.len() < this.MaxMovementCompareSamples" in compare
