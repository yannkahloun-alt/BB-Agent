from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_route_score_smoke_diagnostic_is_not_loaded_during_topology_tdd() -> None:
    preload = _text(PRELOAD)
    assert "scripts/bb_agent/runtime_debug_oracle_route_score" not in preload
    assert "scripts/bb_agent/runtime_debug_oracle_movement_compare" not in preload


def test_topology_probe_is_bounded_before_export() -> None:
    preload = _text(PRELOAD)
    graph = preload.index("scripts/bb_agent/runtime_movement_graph_compat")
    probe = preload.index("scripts/bb_agent/runtime_debug_oracle_ally_jump_probe")
    export = preload.index("scripts/bb_agent/live_export")
    assert graph < probe < export
