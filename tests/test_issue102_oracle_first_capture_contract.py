from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORACLE_FIRST = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox_oracle_first.nut"
)
PLAYER_LEGAL_PHASE = (
    ROOT
    / "companion_mod/scripts/bb_agent/runtime_combat_sandbox_player_legal_phase.nut"
)
RECOVERY = ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox_recovery.nut"
HOOK = ROOT / "companion_mod/scripts/bb_agent/hooks/tactical_state.nut"
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
CAPTURE = ROOT / "companion_mod/scripts/bb_agent/capture_substrate.nut"
ENTITY_COMPAT = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_entity_fingerprint_compat.nut"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_player_legal_visibility_is_captured_without_a_second_begin_traversal() -> None:
    text = _text(PLAYER_LEGAL_PHASE)
    begin = text.index("sandbox.begin = function(_raw)")
    release = text.index("sandbox._reconcileBoundaryActors", begin)
    begin_body = text[begin:release]
    assert "::BBAGENT_PlayerLegal.build" not in begin_body
    assert "PlayerVisibleNonOwnedActors" in text
    assert "_reconcileBoundaryActors" in text
    capture = _text(CAPTURE)
    assert "PendingPlayerVisibleNonOwnedActors" in capture
    assert "foreach (actor in group)" in capture
    assert "this.State.PendingPlayerVisibleNonOwnedActors = visibleNonOwned" in capture
    compat = _text(ENTITY_COMPAT)
    assert "this.State.PendingPlayerVisibleNonOwnedActors = visibleNonOwned" in compat
    assert "player_legal_boundary_memory" in begin_body
    assert "::BBAGENT_Capture.getObservationMemory()" in begin_body
    assert "player_legal_publication_deferred=last" in _text(ORACLE_FIRST)


def test_boundary_visibility_wins_over_stale_actor_memory() -> None:
    text = _text(PLAYER_LEGAL_PHASE)
    restore = text.index("::BBAGENT_Capture.State.ObservationMemory =")
    visible = text.index("foreach (fact in _raw.PlayerVisibleNonOwnedActors)")
    remembered = text.index(
        "foreach (key, memoryFact in ::BBAGENT_Capture.getObservationMemory())"
    )
    skip = text.index("if (memoryFact.Value.actor_id in visibleActorIds) continue;")
    assert restore < visible < remembered < skip
    assert "visible = true" in text[visible:remembered]
    assert "position = wire.exactObserved(fact.tile_id)" in text[visible:remembered]
    assert "last_seen = null" in text[visible:remembered]


def test_duplicate_begin_does_not_reset_player_legal_phase_state() -> None:
    text = _text(PLAYER_LEGAL_PHASE)
    begin = text.index("sandbox.begin = function(_raw)")
    release = text.index("sandbox._reconcileBoundaryActors", begin)
    begin_body = text[begin:release]
    assert "local priorState = this.State;" in begin_body
    assert "if (this.State == null || this.State == priorState) return;" in begin_body
    guard = begin_body.index("this.State == priorState")
    filtering = begin_body.index("local filtered = [];")
    assert guard < filtering


def test_player_legal_phase_publishes_only_after_oracle_queue_drains() -> None:
    text = _text(PLAYER_LEGAL_PHASE)
    assert 'if (job.kind == "player_legal_build") continue;' in text
    assert "player_legal_phase_scheduled <- false" in text
    assert "player_legal_phase_complete <- false" in text
    assert "local originalEnqueueManifestJobs = sandbox._enqueueManifestJobs;" in text
    assert "if (!this.State.player_legal_phase_complete)" in text
    assert "if (!this.State.player_legal_phase_scheduled)" in text
    assert 'this._enqueue("player_legal_build", null, null, null, null, false);' in text
    assert "oracle_jobs_drained=true" in text
    assert "this._enqueueProjectionRecords(projection);" in text
    process = text[text.index("sandbox._processJob = function(_job)") :]
    assert "::BBAGENT_PlayerLegal.build(this.State.raw)" in process
    assert "this.State.player_legal_phase_complete = true;" in text
    assert "return originalEnqueueManifestJobs.acall([this]);" in text


def test_player_legal_build_has_coarse_responsiveness_markers() -> None:
    text = _text(PLAYER_LEGAL_PHASE)
    begin = text.index("player_legal_build_begin")
    call = text.index("this._enqueueProjectionRecords(projection)")
    end = text.index("player_legal_build_end")
    assert begin < call < end
    assert 'local wasPlayerLegalBuild = _job.kind == "player_legal_build";' in text


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


def test_recovery_layer_loads_after_true_player_legal_phase_and_continuity() -> None:
    text = _text(PRELOAD)
    fidelity = text.index("runtime_combat_sandbox_fidelity")
    oracle_first = text.index("runtime_combat_sandbox_oracle_first")
    player_legal_phase = text.index("runtime_combat_sandbox_player_legal_phase")
    bounds = text.index("runtime_combat_sandbox_bounds")
    continuity = text.index("runtime_combat_sandbox_continuity")
    recovery = text.index("runtime_combat_sandbox_recovery")
    assert fidelity < oracle_first < player_legal_phase < bounds < continuity < recovery


def test_debug_oracle_suppresses_normal_live_export_work() -> None:
    text = _text(HOOK)
    assert "if (!::BBAGENT_DebugOracle.Enabled)" in text
    assert "::BBAGENT_LiveExport.handleLifecycleEvent(event);" in text
