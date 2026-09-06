from __future__ import annotations

import json
from dataclasses import fields, replace
from pathlib import Path

import pytest

from bb_agent.live_canonical import (
    live_battle_id,
    live_source_generation,
    materialize_live_tactical_state,
    producer_live_battle_id,
)
from bb_agent.live_ingest import (
    AcceptedLiveDecision,
    LiveCompatibility,
    LiveIngestMachine,
    LiveIngestStatus,
    LiveRecord,
    LiveRecordType,
    decode_live_frame,
    encode_live_frame,
)
from bb_agent.tactical_state import TacticalState

FIXTURE = Path(__file__).parent / "fixtures/ticket_24/t24-core-reload-supported.json"


def _live_state(*, battle_sequence: int = 7, source_generation: int = 3) -> TacticalState:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    state = TacticalState.from_dict(fixture["state"])
    generation = live_source_generation(battle_sequence, source_generation)
    actions = tuple(
        replace(action, source_generation=generation)
        for action in state.action_affordances.actions
    )
    provisional = replace(
        state,
        state_id="",
        raw_capture_id=None,
        battle=replace(
            state.battle, battle_id=producer_live_battle_id(battle_sequence)
        ),
        decision=replace(state.decision, decision_index=source_generation),
        action_affordances=replace(
            state.action_affordances,
            captured_for_state_id="",
            source_generation=generation,
            actions=actions,
        ),
    )
    values = {
        field.name: getattr(provisional, field.name) for field in fields(TacticalState)
    }
    return TacticalState.create(**values)


def _record(
    state: TacticalState,
    *,
    battle_sequence: int = 7,
    source_generation: int = 3,
) -> LiveRecord:
    return LiveRecord(
        record_type=LiveRecordType.DECISION_READY,
        companion_version="0.2.0",
        runtime_game_version="1.5.2.2",
        ruleset_game_version=state.ruleset.game_version,
        ruleset_content_fingerprint=state.ruleset.content_fingerprint,
        mods=(),
        battle_sequence=battle_sequence,
        source_generation=source_generation,
        raw_source_fingerprint="a" * 64,
        information_profile="player_legal",
        payload=state.to_dict(),
    )


def _accepted(
    record: LiveRecord, *, capture_stream_id: str = "stream-test"
) -> AcceptedLiveDecision:
    compatibility = LiveCompatibility(
        ruleset_game_version=record.ruleset_game_version,
        ruleset_content_fingerprint=record.ruleset_content_fingerprint,
        expected_mods=(),
        expected_companion_version=record.companion_version,
        expected_runtime_game_version=record.runtime_game_version,
    )
    machine = LiveIngestMachine(
        compatibility, stream_id_factory=lambda: capture_stream_id
    )
    start = LiveRecord(
        record_type=LiveRecordType.STREAM_START,
        companion_version=record.companion_version,
        runtime_game_version=record.runtime_game_version,
        ruleset_game_version=record.ruleset_game_version,
        ruleset_content_fingerprint=record.ruleset_content_fingerprint,
        mods=record.mods,
        kernel_identity=record.kernel_identity,
    )
    assert machine.accept(start).status is LiveIngestStatus.STREAM_STARTED

    decoded = decode_live_frame(encode_live_frame(record))
    event = machine.accept(decoded)
    assert event.status is LiveIngestStatus.READY
    assert event.decision is not None
    return event.decision


def test_materialize_decoded_ready_thaws_payload_and_binds_host_identities() -> None:
    source = _live_state()
    accepted = _accepted(_record(source))

    materialized = materialize_live_tactical_state(accepted)

    assert materialized.raw_capture_id == accepted.raw_capture_id
    assert materialized.state_id != source.state_id
    assert materialized.battle.battle_id == live_battle_id("stream-test", 7)
    assert materialized.decision.decision_index == 3
    assert materialized.action_affordances.source_generation == "live:7:3"
    assert all(
        action.source_generation == "live:7:3"
        for action in materialized.action_affordances.actions
    )


def test_capture_stream_identity_scopes_final_battle_and_state_ids() -> None:
    source = _live_state()
    record = _record(source)

    first = materialize_live_tactical_state(
        _accepted(record, capture_stream_id="stream-a")
    )
    second = materialize_live_tactical_state(
        _accepted(record, capture_stream_id="stream-b")
    )

    assert first.battle.battle_id != second.battle.battle_id
    assert first.state_id != second.state_id


def test_materialize_rejects_producer_supplied_raw_capture_id() -> None:
    source = _live_state()
    payload = source.to_dict()
    payload["raw_capture_id"] = "b" * 64
    record = replace(_record(source), payload=payload)

    with pytest.raises(ValueError, match="leave raw_capture_id null"):
        materialize_live_tactical_state(_accepted(record))


def test_materialize_rejects_envelope_generation_disagreement() -> None:
    source = _live_state(source_generation=4)
    record = _record(source, source_generation=3)

    with pytest.raises(ValueError, match="decision index disagrees"):
        materialize_live_tactical_state(_accepted(record))
