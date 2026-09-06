from bb_agent.debug_oracle import PairedLiveIngestMachine
from bb_agent.live_ingest import (
    LiveCompatibility,
    LiveIngestStatus,
    LiveRecord,
    LiveRecordType,
)

GAME_VERSION = "scripts-162f498ac7c49b4c317bbf54718a595ecef6a65a"
CONTENT = "4c4b714832d1989740a6f07dce058c11aa1e9123056966ede06ce42d1df182bd"
COMPANION = "bb-agent-companion.v1"
RAW = "a" * 64


def _compat(*, allow_debug: bool) -> LiveCompatibility:
    return LiveCompatibility(
        GAME_VERSION,
        CONTENT,
        expected_mods=(),
        expected_companion_version=COMPANION,
        allow_debug=allow_debug,
    )


def _stream() -> LiveRecord:
    return LiveRecord(
        record_type=LiveRecordType.STREAM_START,
        companion_version=COMPANION,
        runtime_game_version="runtime-test",
        ruleset_game_version=GAME_VERSION,
        ruleset_content_fingerprint=CONTENT,
        mods=(),
    )


def _ready(profile: str, generation: int = 1, marker: str = "base") -> LiveRecord:
    return LiveRecord(
        record_type=LiveRecordType.DECISION_READY,
        companion_version=COMPANION,
        runtime_game_version="runtime-test",
        ruleset_game_version=GAME_VERSION,
        ruleset_content_fingerprint=CONTENT,
        mods=(),
        battle_sequence=1,
        source_generation=generation,
        raw_source_fingerprint=RAW,
        information_profile=profile,
        payload={"marker": marker, "generation": generation},
    )


def _invalidated(generation: int = 1) -> LiveRecord:
    return LiveRecord(
        record_type=LiveRecordType.DECISION_INVALIDATED,
        companion_version=COMPANION,
        runtime_game_version="runtime-test",
        ruleset_game_version=GAME_VERSION,
        ruleset_content_fingerprint=CONTENT,
        mods=(),
        battle_sequence=1,
        source_generation=generation,
        reason="action_resolving",
    )


def test_debug_rejection_never_clears_production_decision() -> None:
    paired = PairedLiveIngestMachine(
        _compat(allow_debug=False), stream_id_factory=lambda: "stream"
    )
    assert paired.accept(_stream()).status is LiveIngestStatus.STREAM_STARTED
    production = paired.accept(_ready("player_legal"))
    assert production.status is LiveIngestStatus.READY
    assert paired.current_decision == production.decision

    rejected = paired.accept(_ready("omniscient_debug", marker="oracle"))
    assert rejected.status is LiveIngestStatus.REJECTED_INCOMPATIBLE
    assert paired.current_decision == production.decision
    assert paired.current_debug_decision is None


def test_debug_twin_is_correlated_but_non_authoritative() -> None:
    paired = PairedLiveIngestMachine(
        _compat(allow_debug=True), stream_id_factory=lambda: "stream"
    )
    paired.accept(_stream())
    production = paired.accept(_ready("player_legal"))
    debug = paired.accept(_ready("omniscient_debug", marker="oracle"))

    assert production.status is LiveIngestStatus.READY
    assert debug.status is LiveIngestStatus.READY
    assert production.decision is not None
    assert debug.decision is not None
    assert production.decision.capture_stream_id == debug.decision.capture_stream_id
    assert production.decision.raw_capture_id == debug.decision.raw_capture_id
    assert paired.current_decision == production.decision
    assert paired.current_debug_decision == debug.decision


def test_debug_conflict_does_not_damage_production_plane() -> None:
    paired = PairedLiveIngestMachine(
        _compat(allow_debug=True), stream_id_factory=lambda: "stream"
    )
    paired.accept(_stream())
    production = paired.accept(_ready("player_legal"))
    paired.accept(_ready("omniscient_debug", marker="oracle-a"))

    conflict = paired.accept(_ready("omniscient_debug", marker="oracle-b"))
    assert conflict.status is LiveIngestStatus.REJECTED_CONFLICT
    assert paired.current_decision == production.decision
    assert paired.current_debug_decision is None


def test_debug_can_arrive_before_production_twin_without_advancing_advice() -> None:
    paired = PairedLiveIngestMachine(
        _compat(allow_debug=True), stream_id_factory=lambda: "stream"
    )
    paired.accept(_stream())
    debug = paired.accept(_ready("omniscient_debug", marker="oracle"))
    assert debug.status is LiveIngestStatus.READY
    assert paired.current_decision is None
    assert paired.current_debug_decision == debug.decision

    production = paired.accept(_ready("player_legal"))
    assert production.status is LiveIngestStatus.READY
    assert paired.current_decision == production.decision
    assert paired.current_debug_decision == debug.decision


def test_production_invalidation_clears_both_planes() -> None:
    paired = PairedLiveIngestMachine(
        _compat(allow_debug=True), stream_id_factory=lambda: "stream"
    )
    paired.accept(_stream())
    paired.accept(_ready("player_legal"))
    paired.accept(_ready("omniscient_debug", marker="oracle"))

    invalidated = paired.accept(_invalidated())
    assert invalidated.status is LiveIngestStatus.INVALIDATED
    assert paired.current_decision is None
    assert paired.current_debug_decision is None


def test_debug_older_than_authoritative_generation_is_rejected_stale() -> None:
    paired = PairedLiveIngestMachine(
        _compat(allow_debug=True), stream_id_factory=lambda: "stream"
    )
    paired.accept(_stream())
    paired.accept(_ready("player_legal", generation=2))

    stale = paired.accept(_ready("omniscient_debug", generation=1, marker="old"))
    assert stale.status is LiveIngestStatus.REJECTED_STALE
    assert paired.current_decision is not None
    assert paired.current_decision.record.source_generation == 2
