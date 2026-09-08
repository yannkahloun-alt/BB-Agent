from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
BOUNDS = ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox_bounds.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_bounds_load_immediately_after_full_sandbox() -> None:
    preload = _text(PRELOAD)
    sandbox = preload.index("scripts/bb_agent/runtime_combat_sandbox")
    bounds = preload.index("scripts/bb_agent/runtime_combat_sandbox_bounds")
    export = preload.index("scripts/bb_agent/live_export")
    assert sandbox < bounds < export


def test_reflection_has_global_node_budget_not_only_per_container_limits() -> None:
    text = _text(BOUNDS)
    for token in (
        "MaxReflectNodes <- 2048",
        "ReflectBudgetActive <- false",
        "ReflectBudgetRemaining <- 0",
        "this.ReflectBudgetRemaining = this.MaxReflectNodes",
        "if (this.ReflectBudgetRemaining <= 0)",
        'reason = "max_nodes"',
        "originalReflect.acall([this, _value, _depth])",
    ):
        assert token in text


def test_one_logical_record_has_hard_size_bound() -> None:
    text = _text(BOUNDS)
    assert "sandbox.MaxDecodedRecordBytes = 32768" in text
    assert "sandbox.MaxEncodedRecordBytes = 49152" in text
