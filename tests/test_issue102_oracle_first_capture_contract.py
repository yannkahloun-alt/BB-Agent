from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORACLE_FIRST = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox_oracle_first.nut"
)
HOOK = ROOT / "companion_mod/scripts/bb_agent/hooks/tactical_state.nut"
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_oracle_first_capture_defers_player_legal_projection() -> None:
    text = _text(ORACLE_FIRST)
    assert 'job.kind != "player_legal_build"' in text
    assert "delete this.State.player_legal_projection;" in text


def test_state_field_sharding_skips_executable_runtime_scaffolding() -> None:
    text = _text(ORACLE_FIRST)
    assert "sandbox._sandboxStateFieldKind <- function(_value)" in text
    for kind in (
        '"function"',
        '"nativeclosure"',
        '"class"',
        '"thread"',
        '"generator"',
        '"userdata"',
        '"weakref"',
    ):
        assert kind in text
    assert "omitted_runtime_field_count" in text
    assert "omitted_runtime_fields" in text


def test_oracle_first_layer_loads_after_fidelity_before_bounds() -> None:
    text = _text(PRELOAD)
    fidelity = text.index("runtime_combat_sandbox_fidelity")
    oracle_first = text.index("runtime_combat_sandbox_oracle_first")
    bounds = text.index("runtime_combat_sandbox_bounds")
    assert fidelity < oracle_first < bounds


def test_debug_oracle_suppresses_normal_live_export_work() -> None:
    text = _text(HOOK)
    assert "if (!::BBAGENT_DebugOracle.Enabled)" in text
    assert "::BBAGENT_LiveExport.handleLifecycleEvent(event);" in text
