from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
EXPORT = ROOT / "companion_mod/scripts/bb_agent/live_export.nut"
HOOK = ROOT / "companion_mod/scripts/bb_agent/hooks/tactical_state.nut"
SANDBOX = ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox.nut"


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
        "::BBAGENT_CombatSandbox.cancel(\"battle_ended\");",
        "::BBAGENT_CombatSandbox.cancel(\"tactical_state_finished\");",
    ):
        assert token in hook

    begin = hook.index("::BBAGENT_CombatSandbox.begin(raw);")
    pump = hook.index("::BBAGENT_CombatSandbox.pump();")
    export = hook.index("::BBAGENT_LiveExport.handleLifecycleEvent(event);")
    assert begin < pump < export


def test_snapshot_pump_is_one_bounded_job_per_update() -> None:
    text = _text(SANDBOX)
    for token in (
        "RecordsPerPump = 1",
        "function begin(_raw)",
        "function pump()",
        "function cancel(_reason)",
        "function _processJob(_job)",
        "this.State.cursor",
        "this.State.jobs",
    ):
        assert token in text

    pump = text[text.index("function pump()") :]
    assert "while (processed < this.RecordsPerPump" in pump


def test_heavy_actor_and_projection_data_are_split_into_independent_records() -> None:
    text = _text(SANDBOX)
    for token in (
        'kind = "actor_core"',
        'kind = "actor_state"',
        'kind = "actor_properties"',
        'kind = "actor_skills_container"',
        'kind = "actor_skill"',
        'kind = "actor_items_container"',
        'kind = "actor_item"',
        'kind = "actor_ai"',
        'kind = "tile"',
        'kind = "raw_fingerprint_input"',
        'kind = "observation_memory"',
        'kind = "player_legal_build"',
        'kind = "player_legal_meta"',
        'kind = "player_legal_tile"',
        'kind = "player_legal_actor"',
    ):
        assert token in text


def test_manifest_is_sharded_and_emitted_only_after_all_jobs_complete() -> None:
    text = _text(SANDBOX)
    for token in (
        "ManifestShardSize = 64",
        'kind = "manifest_expected"',
        'kind = "manifest_root"',
        "expected_record_count",
        "expected_shards",
        "this.State.finalizing",
    ):
        assert token in text


def test_generation_change_aborts_instead_of_mixing_combat_states() -> None:
    text = _text(SANDBOX)
    for token in (
        "capture.getCurrentRawAcquisition()",
        "current.BattleSequence != this.State.battle_sequence",
        "current.SourceGeneration != this.State.source_generation",
        'this.cancel("generation_changed")',
    ):
        assert token in text


def test_preload_contains_only_full_combat_forensic_snapshot() -> None:
    preload = _text(PRELOAD)
    assert "runtime_combat_sandbox" in preload
    for forbidden in (
        "runtime_movement_sandbox",
        "runtime_debug_oracle_movement_compare",
        "runtime_debug_oracle_ally_jump_probe",
        "runtime_debug_oracle_route_score",
        "runtime_navigator_tiebreak_compat",
    ):
        assert forbidden not in preload
