from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
SANDBOX = ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_full_combat_sandbox_loads_without_old_path_or_scheduler_overrides() -> None:
    preload = _text(PRELOAD)
    assert "scripts/bb_agent/runtime_combat_sandbox" in preload
    assert "scripts/bb_agent/runtime_debug_oracle_ally_jump_probe" in preload
    for forbidden in (
        "runtime_combat_sandbox_incremental",
        "runtime_movement_sandbox",
        "runtime_debug_oracle_movement_compare",
        "runtime_debug_oracle_tiebreak_samples",
        "runtime_debug_oracle_route_score",
    ):
        assert forbidden not in preload


def test_snapshot_scope_is_omniscient_full_tactical_state() -> None:
    text = _text(SANDBOX)
    for token in (
        'FramePrefix = "BBCOMBAT1"',
        'SchemaVersion = "bb-agent-combat-sandbox.v1"',
        "_raw.EntityManager.getAllInstances()",
        "::Tactical.getMapSize()",
        "::Tactical.getTileSquare(x, y)",
        "_tile.IsVisibleForPlayer",
        "_tile.IsDiscovered",
        "_tile.IsEmpty",
        "_tile.getEntity()",
        "_actor.isHiddenToPlayer()",
        "_job.target.getCurrentProperties()",
        "_job.target.getBaseProperties()",
        "actor.getSkills().m.Skills",
        "actor.getItems().getAllItems()",
        "_job.target.getAIAgent()",
        "capture.getObservationMemory()",
        "_raw.RawSourceFingerprintInputs",
        "raw.TacticalState.m",
        "raw.TurnSequenceBar.m",
        "raw.EntityManager.m",
        "this._reflect(::Tactical)",
        "this._reflect(raw.Navigator)",
        "_active.getActionPointCosts()",
        "_active.getFatigueCosts()",
        "properties.FatigueEffectMult",
        "wire.canonicalHash(_raw.RawSourceFingerprintInputs)",
    ):
        assert token in text


def test_reflective_dump_is_bounded_and_preserves_runtime_types() -> None:
    text = _text(SANDBOX)
    for token in (
        "MaxReflectDepth = 6",
        "MaxReflectEntries = 512",
        '__bb_type = "float"',
        "_value.tostring()",
        "__bb_truncated = true",
        'this._omitted(kind, "nested_instance")',
        "marker.state <- this._reflect(_value.m, _depth + 1)",
    ):
        assert token in text


def test_each_record_uses_small_integrity_checked_log_chunks() -> None:
    text = _text(SANDBOX)
    for token in (
        "ChunkPayloadChars = 1200",
        "MaxChunkLineBytes = 1500",
        "wire.sha256(raw)",
        "wire.base64Url(raw)",
        'this.FramePrefix + "|"',
        "raw.len().tostring()",
        "::logInfo(line);",
    ):
        assert token in text
    assert "::logInfo(frame);" not in text


def test_snapshot_is_debug_only_and_never_invokes_native_pathfinding() -> None:
    text = _text(SANDBOX)
    assert "oracle.Enabled" in text
    assert "navigator.findPath(" not in text
    assert "navigator.getCostForPath(" not in text
    assert "omniscient_debug" in text
