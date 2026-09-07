from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
PROBE = ROOT / "companion_mod/scripts/bb_agent/runtime_debug_oracle_ally_jump_probe.nut"
ROSTER_PROBE = (
    ROOT
    / "companion_mod/scripts/bb_agent/runtime_debug_oracle_ally_jump_roster_probe.nut"
)
GRAPH = ROOT / "companion_mod/scripts/bb_agent/runtime_movement_graph_compat.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ally_jump_probe_loads_after_full_oracle_layers_before_live_export() -> None:
    preload = _text(PRELOAD)
    graph = preload.index("scripts/bb_agent/runtime_movement_graph_compat")
    sandbox = preload.index("scripts/bb_agent/runtime_combat_sandbox")
    recovery = preload.index("scripts/bb_agent/runtime_combat_sandbox_recovery")
    probe = preload.index("scripts/bb_agent/runtime_debug_oracle_ally_jump_probe")
    roster_probe = preload.index(
        "scripts/bb_agent/runtime_debug_oracle_ally_jump_roster_probe"
    )
    export = preload.index("scripts/bb_agent/live_export")
    assert graph < sandbox < recovery < probe < roster_probe < export
    assert "scripts/bb_agent/runtime_debug_oracle_movement_compare" not in preload


def test_probe_is_single_sample_debug_only_and_never_supplies_values() -> None:
    text = _text(PROBE)
    graph = _text(GRAPH)

    for token in (
        "oracle.LastAllyJumpProbeKey <- null;",
        "if (!this.Enabled) return;",
        "_tree.unresolved_jump_edges",
        "local edge = _tree.unresolved_jump_edges[0];",
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


def test_probe_runs_during_deferred_player_legal_sandbox_phase() -> None:
    text = _text(PROBE)
    assert 'local wasPlayerLegalBuild = _job.kind == "player_legal_build";' in text
    assert "this.State.player_legal_projection == null" in text
    assert "affordances._movementReachability(" in text
    assert '"ally_jump_probe_record"' in text


def test_probe_result_is_expected_sandbox_record_not_production_payload() -> None:
    text = _text(PROBE)
    assert '"debug_probe"' in text
    assert '"ally_jump"' in text
    assert "oracle.LastAllyJumpProbeRecord" in text
    assert (
        "this._emitRecord(this.State.raw, _job.section, _job.key, _job.target);" in text
    )
    assert "this._enqueue(" in text
    assert "resource_cost_resolved = false" in _text(GRAPH)


def test_roster_probe_only_uses_owned_live_turn_actors() -> None:
    text = _text(ROSTER_PROBE)
    assert "_raw.TurnSequenceBar.getCurrentEntities()" in text
    assert "actor.isPlayerControlled()" in text
    assert "actor.isAlive()" in text
    assert "actor.isPlacedOnMap()" in text
    assert "probeRaw.ActiveActor = actor;" in text
    assert "probeProjection.runtime.active_actor_id = legal.actorID(actor);" in text


def test_roster_probe_replaces_only_debug_sandbox_record() -> None:
    text = _text(ROSTER_PROBE)
    assert 'job.kind != "ally_jump_probe_record"' in text
    assert 'job.section != "debug_probe" || job.key != "ally_jump"' in text
    assert "job.target = replacement;" in text
    assert "BBAGENT1|" not in text
    assert "information_profile" not in text
    assert "record.payload" not in text


def test_roster_probe_stops_after_first_native_candidate() -> None:
    text = _text(ROSTER_PROBE)
    assert "if (record == null" in text
    assert "!record.candidate" in text
    assert "return record;" in text
    assert 'reason = "no_candidate_across_owned_roster"' in text
