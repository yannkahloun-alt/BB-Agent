from __future__ import annotations

from pathlib import Path

from bb_agent.live_ingest import current_live_kernel_identity

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
WIRE = ROOT / "companion_mod/scripts/bb_agent/canonical_wire.nut"
PROJECTION = ROOT / "companion_mod/scripts/bb_agent/player_legal_projection.nut"
PROJECTION_HARDENING = (
    ROOT / "companion_mod/scripts/bb_agent/player_legal_hardening.nut"
)
IDENTITY = ROOT / "companion_mod/scripts/bb_agent/canonical_identity.nut"
AFFORDANCES = ROOT / "companion_mod/scripts/bb_agent/affordance_export.nut"
AFFORDANCE_HARDENING = (
    ROOT / "companion_mod/scripts/bb_agent/affordance_export_hardening.nut"
)
EXPORT = ROOT / "companion_mod/scripts/bb_agent/live_export.nut"
HOOK = ROOT / "companion_mod/scripts/bb_agent/hooks/tactical_state.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_preload_orders_projection_and_export_before_tactical_hook() -> None:
    source = _text(PRELOAD)
    assert 'Version = "0.2.8"' in source
    modules = (
        "canonical_wire",
        "player_legal_projection",
        "player_legal_hardening",
        "canonical_identity",
        "affordance_export",
        "affordance_export_hardening",
        "live_export",
        "hooks/tactical_state",
    )
    offsets = [source.index(f"scripts/bb_agent/{module}") for module in modules]
    assert offsets == sorted(offsets)


def test_wire_identity_matches_closed_m1_kernel() -> None:
    source = _text(WIRE)
    for key, value in current_live_kernel_identity().to_wire_dict().items():
        assert f'{key} = "{value}"' in source
    assert 'EnvelopeVersion = "bb-agent-live-envelope.v1"' in source
    assert 'CaptureContractVersion = "bb-agent-live-capture.v1"' in source
    assert 'FramePrefix = "BBAGENT1"' in source
    assert 'if (kind == "float") throw' in source


def test_player_legal_projection_keeps_hidden_truth_out_of_normal_payload() -> None:
    source = _text(PROJECTION)
    hardening = _text(PROJECTION_HARDENING)
    assert (
        "resources = owned ? this._ownedResources(_actor) : this._unknownResources()"
        in source
    )
    assert "tactical_stats = owned ? this._ownedStats(_actor) : []" in source
    assert "perks = owned ?" in source
    assert "traits = owned ?" in source
    assert '"actor-memory:" + actorId' in source
    assert '"tile-memory:" + id' in source
    assert "position = wire.unknownValue()" in source
    assert "last_seen = {" in source
    assert "delete sanitized.faction;" in hardening
    assert "projected.faction = wire.unknownValue();" in hardening
    assert "faction = wire.unknownValue()" in hardening
    assert (
        "if (!_actor.isAlive() || !_actor.isPlacedOnMap()) return false;" in hardening
    )
    assert "sequence = wire.exactObserved(entries.len())" in hardening
    assert "DEBUG_GROUND_TRUTH" not in source
    assert "DEBUG_ORACLE" not in source


def test_canonical_identity_matches_existing_action_and_state_identity_boundaries() -> (
    None
):
    source = _text(IDENTITY)
    direct_fields = (
        "actor_id",
        "kind",
        "skill_id",
        "item_id",
        "target_kind",
        "target_actor_id",
        "target_tile_id",
        "target_direction",
        "mode_variant",
        "destination_tile_id",
        "source_location",
        "target_slot",
        "displaced_item_id",
        "displaced_item_destination",
    )
    for field in direct_fields:
        assert f"{field} = _action.{field}" in source
    assert "parameters = this._cloneJson(_action.parameters)" in source
    assert "resolved_path = this._cloneJson(_action.resolved_path)" in source
    for removed in (
        "state_id",
        "raw_capture_id",
        "annotations",
        "captured_for_state_id",
        "source_generation",
        "debug_ground_truth",
        "provenance",
    ):
        assert "delete " in source and removed in source
    assert '"action:" + wire.canonicalHash(this._actionIntent(_action))' in source


def test_affordance_acquisition_uses_game_authority_and_never_executes_commands() -> (
    None
):
    source = _text(AFFORDANCES)
    hardening = _text(AFFORDANCE_HARDENING)
    for required in (
        "queryActives()",
        "skill.isUsable()",
        "skill.isAffordable()",
        "skill.isUsableOn(tile, active.getTile())",
        "skill.getActionPointCost()",
        "skill.getFatigueCost()",
        "source.getAmmoCost()",
        "navigator.findPath(",
        "navigator.getCostForPath(",
        'this._movementCost(costs, "ActionPointsRequired", "ActionPoints")',
        'this._movementCost(costs, "FatigueRequired", "Fatigue")',
        "navigator.clearPath()",
        "canEntityWait(active)",
        "helper_queryEquipmentTargetItems",
        "helper_isActionAllowed",
        "inventory.isActionAffordable(items)",
        "inventory.getActionCost(items)",
        'unsupported_mechanic_id = "live.player_legal.aoo_probability_unavailable"',
    ):
        assert required in source
    assert "native movement path leaves the player-legal canonical map" in hardening
    assert "this.CurrentProjection.runtime.tile_records" in hardening
    for cost in (
        "ap_cost",
        "fatigue_cost",
        "charge_cost",
        "ammo_cost",
        "item_action_cost",
    ):
        assert f"_action.{cost} = wire.resolvedCost" in source
    assert "wire.resolvedPreview(chance, " not in source
    for forbidden in (
        ".payForAction(",
        ".equip(",
        ".unequip(",
        ".swap(",
        ".use(",
        ".onUse(",
        ".wait(",
        ".endTurn(",
        "initNextTurnBecauseOfWait(",
        "Math.rand(",
    ):
        assert forbidden not in source
        assert forbidden not in hardening


def test_live_export_is_transactional_strict_and_player_legal_only() -> None:
    source = _text(EXPORT)
    hook = _text(HOOK)
    for record_type in ("STREAM_START", "DECISION_READY", "DECISION_INVALIDATED"):
        assert record_type in source
    assert "MaxDecodedRecordBytes = 2097152" in source
    assert "MaxEncodedFrameBytes = 3145728" in source
    assert "StreamStarted = false" in source
    assert "if (this.StreamStarted) return true;" in source
    assert "this._requireStream();" in source
    assert 'local record = this._common("STREAM_START");' in source
    assert "this._emit(record);" in source
    assert 'record.information_profile <- "player_legal"' in source
    assert "capture generation changed during canonical acquisition" in source
    assert "raw source changed during canonical acquisition" in source
    assert 'capture.invalidate("capture_fault")' in source
    assert "::logInfo(frame);" in source
    assert "getCurrentRawAcquisition" in source
    assert "BBAGENT_LiveExport.beginBattle();" in hook
    assert "BBAGENT_LiveExport.handleLifecycleEvent(event);" in hook
    assert "omniscient_debug" not in source
