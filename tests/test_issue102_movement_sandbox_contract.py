from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
EXPORT = ROOT / "companion_mod/scripts/bb_agent/live_export.nut"
SANDBOX = ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox.nut"
INCREMENTAL = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox_incremental.nut"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_full_combat_sandbox_loads_before_live_export_without_path_probes() -> None:
    preload = _text(PRELOAD)
    base = preload.index("scripts/bb_agent/runtime_combat_sandbox")
    incremental = preload.index("scripts/bb_agent/runtime_combat_sandbox_incremental")
    export = preload.index("scripts/bb_agent/live_export")
    assert base < incremental < export
    for forbidden in (
        "runtime_debug_oracle_movement_compare",
        "runtime_debug_oracle_tiebreak_samples",
        "runtime_debug_oracle_route_score",
        "runtime_debug_oracle_ally_jump_probe",
        "runtime_movement_sandbox",
    ):
        assert forbidden not in preload


def test_snapshot_is_started_immediately_after_projection_before_affordances() -> None:
    text = _text(EXPORT)
    projection = text.index("local projection = ::BBAGENT_PlayerLegal.build(_raw);")
    snapshot = text.index("::BBAGENT_CombatSandbox.capture(_raw, projection);")
    acquire = text.index("local actions = ::BBAGENT_Affordances.acquire(_raw, projection);")
    assert projection < snapshot < acquire


def test_snapshot_is_full_debug_state_not_player_legal_only() -> None:
    text = _text(SANDBOX)
    for token in (
        'FramePrefix = "BBCOMBAT1"',
        'SchemaVersion = "bb-agent-combat-sandbox.v1"',
        "_raw.EntityManager.getAllInstances()",
        "::Tactical.getMapSize()",
        "::Tactical.getTileSquare(x, y)",
        "tile.IsVisibleForPlayer",
        "tile.IsDiscovered",
        "tile.IsEmpty",
        "tile.getEntity()",
        "actor.isHiddenToPlayer()",
        "actor.getCurrentProperties()",
        "actor.getBaseProperties()",
        "actor.getSkills().m.Skills",
        "actor.getItems().getAllItems()",
        "actor.getAIAgent()",
        "_projection.state",
        "capture.getObservationMemory()",
        "_raw.RawSourceFingerprintInputs",
        "_raw.ValidationContext",
        "_raw.TacticalState.m",
        "_raw.TurnSequenceBar.m",
        "active.getActionPointCosts()",
        "active.getFatigueCosts()",
        "wire.canonicalHash(_raw.RawSourceFingerprintInputs)",
    ):
        assert token in text


def test_reflective_dump_is_bounded_and_preserves_float_text() -> None:
    text = _text(SANDBOX)
    for token in (
        "MaxReflectDepth = 6",
        "MaxReflectEntries = 512",
        '"__bb_type"',
        '"float"',
        "_value.tostring()",
        '"__bb_truncated"',
    ):
        assert token in text


def test_combat_snapshot_uses_small_integrity_checked_chunk_lines() -> None:
    text = _text(SANDBOX)
    for token in (
        "ChunkPayloadChars = 1200",
        "wire.base64Url(raw)",
        'this.FramePrefix + "|"',
        '::logInfo(line);',
        'this._emitRecord(_raw, "actor"',
        'this._emitRecord(_raw, "tile"',
        '"manifest",',
        '"player_legal",',
    ):
        assert token in text
    assert "::logInfo(frame);" not in text


def test_snapshot_is_debug_only_and_nonfatal() -> None:
    base = _text(SANDBOX)
    incremental = _text(INCREMENTAL)
    assert "oracle.Enabled" in base
    assert "catch (error)" in base
    assert '[BB-Agent Combat Sandbox] error=' in base
    assert "navigator.findPath(" not in base
    assert "navigator.getCostForPath(" not in base
    assert "::TimeUnit.Real" in incremental
    assert "::TimeUnit.Virtual" not in incremental
