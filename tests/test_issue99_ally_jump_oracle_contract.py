from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
PROBE = ROOT / "companion_mod/scripts/bb_agent/runtime_debug_oracle_ally_jump_probe.nut"
GRAPH = ROOT / "companion_mod/scripts/bb_agent/runtime_movement_graph_compat.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ally_jump_probe_is_the_only_loaded_native_movement_probe() -> None:
    preload = _text(PRELOAD)
    graph = preload.index("scripts/bb_agent/runtime_movement_graph_compat")
    probe = preload.index("scripts/bb_agent/runtime_debug_oracle_ally_jump_probe")
    export = preload.index("scripts/bb_agent/live_export")
    assert graph < probe < export
    assert "scripts/bb_agent/runtime_debug_oracle_movement_compare" not in preload


def test_probe_is_single_sample_debug_only_and_never_supplies_values() -> None:
    text = _text(PROBE)
    graph = _text(GRAPH)

    for token in (
        "oracle.LastAllyJumpProbeKey <- null;",
        "if (!this.Enabled) return;",
        "tree.unresolved_jump_edges",
        "local edge = tree.unresolved_jump_edges[0];",
        "navigator.findPath(",
        "navigator.getCostForPath(",
        "ally_jump_probe",
        "two_step_ap=",
        "two_step_fat=",
        "landing_step_ap=",
        "landing_step_fat=",
    ):
        assert token in text

    for forbidden in (
        "BBAGENT1|",
        "encodeFrame(",
        "record.payload",
        "information_profile",
        "omniscient_debug",
    ):
        assert forbidden not in text

    assert "resource_cost_resolved = false" in graph


def test_probe_deduplicates_per_battle_generation() -> None:
    text = _text(PROBE)
    assert "_raw.BattleSequence" in text
    assert "_raw.SourceGeneration" in text
    assert "if (this.LastAllyJumpProbeKey == key) return;" in text
