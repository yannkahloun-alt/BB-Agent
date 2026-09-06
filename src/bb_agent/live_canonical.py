"""Bridge accepted live READY records into the unchanged canonical M1 contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields, replace

from bb_agent.live_ingest import AcceptedLiveDecision
from bb_agent.serialization import JsonValue
from bb_agent.tactical_state import InformationProfile, TacticalState


def live_source_generation(battle_sequence: int, source_generation: int) -> str:
    """Return the canonical generation label used by the game-side live producer."""
    return f"live:{battle_sequence}:{source_generation}"


def producer_live_battle_id(battle_sequence: int) -> str:
    """Return the producer placeholder before host stream identity is available."""
    return f"live-battle:{battle_sequence}"


def live_battle_id(capture_stream_id: str, battle_sequence: int) -> str:
    """Return the final canonical battle identity for one accepted live stream."""
    if not capture_stream_id:
        raise ValueError("capture_stream_id cannot be empty")
    return f"live-battle:{capture_stream_id}:{battle_sequence}"


def _thaw_live_json(value: JsonValue) -> JsonValue:
    """Detach recursively frozen ingest payloads into mutable JSON containers."""
    if isinstance(value, Mapping):
        return {key: _thaw_live_json(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_thaw_live_json(child) for child in value]
    return value


def _create_rebound_state(
    producer_state: TacticalState,
    decision: AcceptedLiveDecision,
) -> TacticalState:
    record = decision.record
    assert record.battle_sequence is not None
    rebound = replace(
        producer_state,
        state_id="",
        raw_capture_id=decision.raw_capture_id,
        battle=replace(
            producer_state.battle,
            battle_id=live_battle_id(
                decision.capture_stream_id, record.battle_sequence
            ),
        ),
        action_affordances=replace(
            producer_state.action_affordances,
            captured_for_state_id="",
        ),
    )
    values = {field.name: getattr(rebound, field.name) for field in fields(TacticalState)}
    return TacticalState.create(**values)


def materialize_live_tactical_state(decision: AcceptedLiveDecision) -> TacticalState:
    """Validate one accepted payload and bind host stream/capture identities.

    The companion cannot know ``capture_stream_id`` or final ``raw_capture_id``.
    It emits a canonical producer placeholder battle ID and ``raw_capture_id=null``.
    This host boundary validates that producer payload unchanged first, then binds
    both host identities and recomputes the final canonical state ID before M1.
    """
    record = decision.record
    if record.payload is None:
        raise ValueError("accepted READY record is missing canonical payload")
    if record.battle_sequence is None or record.source_generation is None:
        raise ValueError("accepted READY record is missing generation identity")
    payload_value = _thaw_live_json(record.payload)
    if not isinstance(payload_value, dict):
        raise ValueError("accepted READY payload must be a canonical object")
    if payload_value.get("raw_capture_id") is not None:
        raise ValueError("producer canonical payload must leave raw_capture_id null")

    producer_state = TacticalState.from_dict(payload_value)
    if producer_state.information_profile.value != record.information_profile:
        raise ValueError("canonical information profile disagrees with live envelope")
    if producer_state.information_profile is not InformationProfile.PLAYER_LEGAL:
        raise ValueError("normal live canonical materialization requires player_legal")
    if producer_state.ruleset.game_version != record.ruleset_game_version:
        raise ValueError("canonical ruleset game version disagrees with live envelope")
    if (
        producer_state.ruleset.content_fingerprint
        != record.ruleset_content_fingerprint
    ):
        raise ValueError("canonical content fingerprint disagrees with live envelope")
    if producer_state.battle.battle_id != producer_live_battle_id(
        record.battle_sequence
    ):
        raise ValueError("producer battle identity disagrees with live generation")
    if producer_state.decision.decision_index != record.source_generation:
        raise ValueError("canonical decision index disagrees with live generation")

    expected_generation = live_source_generation(
        record.battle_sequence, record.source_generation
    )
    if producer_state.action_affordances.source_generation != expected_generation:
        raise ValueError("canonical affordance generation disagrees with live envelope")
    if any(
        action.source_generation != expected_generation
        for action in producer_state.action_affordances.actions
    ):
        raise ValueError("canonical action generation disagrees with live envelope")

    state = _create_rebound_state(producer_state, decision)
    if state.raw_capture_id != decision.raw_capture_id:
        raise ValueError("canonical raw_capture_id disagrees with accepted stream identity")
    if state.battle.battle_id != live_battle_id(
        decision.capture_stream_id, record.battle_sequence
    ):
        raise ValueError("canonical battle identity disagrees with accepted stream")
    return state
