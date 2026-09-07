from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
EXPORT = ROOT / "companion_mod/scripts/bb_agent/live_export.nut"
HOOK = ROOT / "companion_mod/scripts/bb_agent/hooks/tactical_state.nut"
SANDBOX = ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox.nut"
CONTINUITY = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox_continuity.nut"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_full_combat_snapshot_is_not_serialized_inside_ready_export() -> None:
    export = _text(EXPORT)
    assert "BBAGENT_CombatSandbox.capture" not in export
    assert "BBAGENT_CombatSandbox.begin" not in export
    assert "BBAGENT_CombatSandbox.pump" not in export


def test_tactical_update_starts_and_pumps_snapshot_incrementally() -> None:
    hook = _text(HOOK)
    for token in (
        "::BBAGENT_CombatSandbox.begin(raw);",
        "::BBAGENT_CombatSandbox.pump();",
        '::BBAGENT_CombatSandbox.cancel("battle_ended");',
        '::BBAGENT_CombatSandbox.cancel("tactical_state_finished");',
    ):
        assert token in hook

    begin = hook.index("::BBAGENT_CombatSandbox.begin(raw);")
    pump = hook.index("::BBAGENT_CombatSandbox.pump();")
    export = hook.index("::BBAGENT_LiveExport.handleLifecycleEvent(event);")
    assert begin < pump < export


def test_snapshot_pump_is_one_bounded_job_per_update() -> None:
    base = _text(SANDBOX)
    continuity = _text(CONTINUITY)
    for token in (
        "RecordsPerPump = 1",
        "function begin(_raw)",
        "function cancel(_reason)",
        "function _processJob(_job)",
        "this.State.cursor",
        "this.State.jobs",
    ):
        assert token in base

    assert "sandbox.pump = function()" in continuity
    assert "while (processed < this.RecordsPerPump" in continuity


def test_heavy_data_is_split_into_independent_records() -> None:
    text = _text(SANDBOX)
    for token in (
        'this._enqueue("actor_core",',
        'this._enqueue("actor_state",',
        'this._enqueue("actor_properties",',
        'this._enqueue("actor_skills_container",',
        'this._enqueue("actor_skill",',
        'this._enqueue("actor_items_container",',
        'this._enqueue("actor_item",',
        'this._enqueue("actor_ai",',
        'this._enqueue("tile",',
        '"raw_fingerprint_input",',
        '"observation_memory",',
        'this._enqueue("player_legal_build",',
        'this._enqueue("player_legal_meta",',
        'this._enqueue("player_legal_tile",',
        'this._enqueue("player_legal_actor",',
    ):
        assert token in text


def test_manifest_is_sharded_after_all_jobs_complete() -> None:
    text = _text(SANDBOX)
    for token in (
        "ManifestShardSize = 64",
        '"manifest_expected",',
        'this._enqueue("manifest_root",',
        "expected_record_count",
        "expected_shards",
        "this.State.finalizing",
    ):
        assert token in text


def test_failed_ready_latch_does_not_cancel_forensic_generation() -> None:
    text = _text(CONTINUITY)
    for token in (
        "capture._commandReadiness(this.State.raw.TacticalState)",
        "if (!readiness.Ready) return;",
        "capture.State.BattleSequence != this.State.battle_sequence",
        "capture.State.SourceGeneration != this.State.source_generation",
        "capture.State.LastReadySignature != this.State.source_signature",
        'this.cancel("generation_changed")',
        "this.State.source_signature <- capture.State.LastReadySignature;",
    ):
        assert token in text
    assert "capture.getCurrentRawAcquisition()" not in text


def test_individual_read_failures_emit_error_records_and_continue() -> None:
    base = _text(SANDBOX)
    continuity = _text(CONTINUITY)
    assert "function _emitJobError(_job, _error)" in base
    assert "__capture_error = _error.tostring()" in base
    assert "transport_error" in continuity


def test_preload_contains_only_full_combat_forensic_snapshot() -> None:
    preload = _text(PRELOAD)
    assert "runtime_combat_sandbox" in preload
    assert "runtime_combat_sandbox_continuity" in preload
    for forbidden in (
        "runtime_combat_sandbox_incremental",
        "runtime_movement_sandbox",
        "runtime_debug_oracle_movement_compare",
        "runtime_debug_oracle_ally_jump_probe",
        "runtime_debug_oracle_route_score",
        "runtime_navigator_tiebreak_compat",
    ):
        assert forbidden not in preload
