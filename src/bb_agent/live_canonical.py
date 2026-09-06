"""Bridge accepted live READY records into the unchanged canonical M1 contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from bb_agent.live_ingest import AcceptedLiveDecision
from bb_agent.serialization import JsonValue
from bb_agent.tactical_state import InformationProfile, TacticalState


def live_source_generation(battle_sequence: int, source_generation: int) -> str:
    """Return the canonical generation label used by the game-side live producer."""
    return f"live:{battle_sequence}:{source_generation}"


def live_battle_id(battle_sequence: int) -> str:
    """Return the producer-side battle identity scoped by the active live stream."""
    return f"live-battle:{battle_sequence}"


def _thaw_live_json(value: JsonValue) -> JsonValue:
    """Detach recursively frozen ingest payloads into mutable JSON containers."""
    if isinstance(value, Mapping):
        return {key: _thaw_live_json(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_thaw_live_json(child) for child in value]
    return value


def materialize_live_tactical_state(decision: AcceptedLiveDecision) -> TacticalState:
    """Validate one accepted live payload and attach its host capture identity.

    The companion cannot know ``capture_stream_id`` or final ``raw_capture_id``.
    It therefore emits ``raw_capture_id=null`` and the host binds the accepted
    stream identity here before the closed M1 kernel sees the canonical state.
    """
    record = decision.record
    if record.payload is None:
        raise ValueError("accepted READY record is missing canonical payload")
    if record.battle_sequence is None or record.source_generation is None:
        raise ValueError("accepted READY record is missing generation identity")
    payload_value = _thaw_live_json(record.payload)
    if not isinstance(payload_value, dict):
        raise ValueError("accepted READY payload must be a canonical object")
    payload = payload_value
    if payload.get("raw_capture_id") is not None:
        raise ValueError("producer canonical payload must leave raw_capture_id null")

    payload["raw_capture_id"] = decision.raw_capture_id
    state = TacticalState.from_dict(payload)

    if state.raw_capture_id != decision.raw_capture_id:
        raise ValueError(
            "canonical raw_capture_id disagrees with accepted stream identity"
        )
    if state.information_profile.value != record.information_profile:
        raise ValueError("canonical information profile disagrees with live envelope")
    if state.information_profile is not InformationProfile.PLAYER_LEGAL:
        raise ValueError("normal live canonical materialization requires player_legal")
    if state.ruleset.game_version != record.ruleset_game_version:
        raise ValueError("canonical ruleset game version disagrees with live envelope")
    if state.ruleset.content_fingerprint != record.ruleset_content_fingerprint:
        raise ValueError("canonical content fingerprint disagrees with live envelope")
    if state.battle.battle_id != live_battle_id(record.battle_sequence):
        raise ValueError("canonical battle identity disagrees with live generation")
    if state.decision.decision_index != record.source_generation:
        raise ValueError("canonical decision index disagrees with live generation")

    expected_generation = live_source_generation(
        record.battle_sequence, record.source_generation
    )
    if state.action_affordances.source_generation != expected_generation:
        raise ValueError("canonical affordance generation disagrees with live envelope")
    if any(
        action.source_generation != expected_generation
        for action in state.action_affordances.actions
    ):
        raise ValueError("canonical action generation disagrees with live envelope")
    return state
