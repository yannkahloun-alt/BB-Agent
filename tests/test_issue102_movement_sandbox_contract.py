from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
EXPORT = ROOT / "companion_mod/scripts/bb_agent/live_export.nut"
SANDBOX = ROOT / "companion_mod/scripts/bb_agent/runtime_movement_sandbox.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_sandbox_loads_after_graph_before_live_export_without_path_probes() -> None:
    preload = _text(PRELOAD)
    graph = preload.index("scripts/bb_agent/runtime_movement_graph_compat")
    sandbox = preload.index("scripts/bb_agent/runtime_movement_sandbox")
    export = preload.index("scripts/bb_agent/live_export")

    assert graph < sandbox < export
    assert "runtime_debug_oracle_movement_compare" not in preload
    assert "runtime_debug_oracle_tiebreak_samples" not in preload
    assert "runtime_debug_oracle_route_score" not in preload
    assert "runtime_debug_oracle_ally_jump_probe" not in preload


def test_snapshot_is_emitted_before_affordance_acquisition() -> None:
    text = _text(EXPORT)
    projection = text.index("local projection = ::BBAGENT_PlayerLegal.build(_raw);")
    snapshot = text.index("::BBAGENT_MovementSandbox.capture(_raw, projection);")
    acquire = text.index("local actions = ::BBAGENT_Affordances.acquire(_raw, projection);")
    assert projection < snapshot < acquire


def test_snapshot_is_debug_only_player_legal_and_nonfatal() -> None:
    text = _text(SANDBOX)

    for token in (
        'FramePrefix = "BBSANDBOX1"',
        'SchemaVersion = "bb-agent-movement-sandbox.v1"',
        "if (!oracle.Enabled) return;",
        "player_legal_state = _projection.state",
        "active.getActionPointCosts()",
        "active.getFatigueCosts()",
        "active.getLevelActionPointCost()",
        "active.getLevelFatigueCost()",
        "active.getMaxTraversibleLevels()",
        "properties.FatigueEffectMult",
        "properties.IsRooted",
        "properties.IsStunned",
        "affordances._movementVisibleZocCounts(_projection, visibleTiles)",
        "wire.canonicalHash(_raw.RawSourceFingerprintInputs)",
        '::logInfo("[BB-Agent Sandbox] emitted',
        '::logError("[BB-Agent Sandbox] error=',
        "catch (error)",
    ):
        assert token in text

    for forbidden in (
        "getAllInstances",
        "isHiddenToPlayer",
        "getZoneOfControlCountOtherThan",
        "navigator.findPath(",
        "navigator.getCostForPath(",
        "omniscient_debug",
        "DEBUG_GROUND_TRUTH",
        "tile.IsEmpty",
    ):
        assert forbidden not in text


def test_snapshot_serializes_potential_float_movement_numbers_as_strings() -> None:
    text = _text(SANDBOX)
    assert "_numberText" in text
    assert "_numberArray" in text
    assert "value.tostring()" in text
    assert "movement_ap_costs = this._numberArray(active.getActionPointCosts())" in text
    assert "movement_fatigue_costs = this._numberArray(active.getFatigueCosts())" in text
    assert "fatigue_effect_mult = this._numberText(properties.FatigueEffectMult)" in text


def test_snapshot_uses_distinct_frame_prefix_from_live_protocol() -> None:
    text = _text(SANDBOX)
    assert 'FramePrefix = "BBSANDBOX1"' in text
    assert '"BBAGENT1"' not in text
