from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY = ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox_discovery.nut"
FIDELITY = ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox_fidelity.nut"
HOOK = ROOT / "companion_mod/scripts/bb_agent/hooks/tactical_state.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_oracle_first_capture_defers_player_legal_projection() -> None:
    text = _text(DISCOVERY)
    begin = text[text.index("sandbox.begin = function(_raw)") :]
    assert 'this._enqueue("player_legal_build"' not in begin
    assert "player_legal_projection" not in begin


def test_state_field_sharding_skips_executable_runtime_scaffolding() -> None:
    text = _text(FIDELITY)
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


def test_debug_oracle_suppresses_normal_live_export_work() -> None:
    text = _text(HOOK)
    assert "if (!::BBAGENT_DebugOracle.Enabled)" in text
    assert "::BBAGENT_LiveExport.handleLifecycleEvent(event);" in text
