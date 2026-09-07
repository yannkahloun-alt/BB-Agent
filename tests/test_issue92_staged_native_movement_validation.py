from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = ROOT / "companion_mod/scripts/bb_agent"
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
VALIDATION = SCRIPT_ROOT / "runtime_debug_oracle_movement_validation.nut"


def test_native_movement_validation_loads_after_ally_probe_before_export() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    roster = preload.index("runtime_debug_oracle_ally_jump_roster_probe")
    validation = preload.index("runtime_debug_oracle_movement_validation")
    export = preload.index("scripts/bb_agent/live_export")
    assert roster < validation < export


def test_native_movement_validation_is_debug_only_and_staged() -> None:
    text = VALIDATION.read_text(encoding="utf-8")
    assert "MovementValidationSampleCap <- 6" in text
    assert "if (!oracle.Enabled) return ret;" in text
    assert 'if (_job.kind == "movement_validation_sample")' in text
    assert '"debug_oracle_disabled"' in text
    assert '"movement_validation_sample"' in text
    assert '"debug_movement_validation"' in text
    assert "foreach (index, sample in samples)" in text


def test_native_movement_validation_samples_bounded_representative_roles() -> None:
    text = VALIDATION.read_text(encoding="utf-8")
    for role in (
        "nearest_reachable",
        "farthest_reachable",
        "highest_cost_reachable",
        "zoc_entry",
        "zoc_exit",
        "model_unreachable_visible",
    ):
        assert role in text
    assert "if (!tile.IsEmpty) continue;" in text


def test_native_calls_only_exist_in_debug_validation_sample_path() -> None:
    text = VALIDATION.read_text(encoding="utf-8")
    sample_start = text.index("oracle._movementValidationSample <- function")
    process_start = text.index("local originalSandboxProcessJob")
    sample = text[sample_start:process_start]
    assert "navigator.findPath(" in sample
    assert "navigator.getCostForPath(" in sample
    assert "reachability_agreement" in sample
    assert "cost_agreement" in sample

    production_graph = (SCRIPT_ROOT / "runtime_movement_graph_compat.nut").read_text(
        encoding="utf-8"
    )
    assert "findPath(" not in production_graph
    assert "getCostForPath(" not in production_graph
