from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORACLE_FIRST = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox_oracle_first.nut"
)
RECOVERY = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox_recovery.nut"
)
HOOK = ROOT / "companion_mod/scripts/bb_agent/hooks/tactical_state.nut"
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_oracle_first_capture_runs_player_legal_projection_last() -> None:
    text = _text(ORACLE_FIRST)
    assert (
        'if (job.kind == "player_legal_build") deferredPlayerLegal = job;' in text
    )
    assert "filtered.push(deferredPlayerLegal);" in text
    assert 'job.kind != "player_legal_build"' not in text
    assert "delete this.State.player_legal_projection;" not in text


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


def test_simple_scalar_state_is_packed_without_losing_values() -> None:
    text = _text(ORACLE_FIRST)
    assert "sandbox._sandboxScalarValue <- function(_value)" in text
    assert "sandbox._enqueueScalarPack <- function" in text
    assert '"state_scalar_pack"' in text
    assert "scalar_field_count" in text
    assert "scalar_pack_record_id" in text
    assert "value = scalar.value" in text
    assert "this._floatValue(_value)" in text


def test_native_instance_iteration_limit_is_explicit_not_quality_error() -> None:
    text = _text(ORACLE_FIRST)
    assert 'message == "_nexti failed"' in text
    assert 'iterationUnavailable = "native_instance_not_enumerable"' in text
    assert "iteration_unavailable_reason" in text


def test_all_emitted_payloads_are_float_safe() -> None:
    text = _text(RECOVERY)
    assert "sandbox._sandboxJsonSafe <- function(_value)" in text
    assert 'if (kind == "float") return this._floatValue(_value);' in text
    assert "sandbox._emitRecord = function(_raw, _section, _key, _payload)" in text
    assert "this._sandboxJsonSafe(_payload)" in text


def test_oversized_state_fields_retry_with_smaller_reflection_budget() -> None:
    text = _text(RECOVERY)
    assert "sandbox._sandboxReflectWithNodeBudget <- function" in text
    assert "foreach (nodeBudget in [2048, 512, 128])" in text
    assert 'message != "combat sandbox record exceeds decoded payload bound"' in text
    assert "reflection_node_budget = nodeBudget" in text


def test_recovery_layer_loads_after_bounds_and_continuity() -> None:
    text = _text(PRELOAD)
    fidelity = text.index("runtime_combat_sandbox_fidelity")
    oracle_first = text.index("runtime_combat_sandbox_oracle_first")
    bounds = text.index("runtime_combat_sandbox_bounds")
    continuity = text.index("runtime_combat_sandbox_continuity")
    recovery = text.index("runtime_combat_sandbox_recovery")
    assert fidelity < oracle_first < bounds < continuity < recovery


def test_debug_oracle_suppresses_normal_live_export_work() -> None:
    text = _text(HOOK)
    assert "if (!::BBAGENT_DebugOracle.Enabled)" in text
    assert "::BBAGENT_LiveExport.handleLifecycleEvent(event);" in text
