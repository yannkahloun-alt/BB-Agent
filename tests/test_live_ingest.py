import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from bb_agent.live_ingest import (
    LIVE_CAPTURE_VERSION,
    LIVE_ENVELOPE_VERSION,
    LiveCompatibility,
    LiveIngestMachine,
    LiveIngestStatus,
    LiveLogTailer,
    LiveRecord,
    LiveRecordType,
    current_live_kernel_identity,
    decode_live_frame,
    encode_live_frame,
)

GAME_VERSION = "scripts-162f498ac7c49b4c317bbf54718a595ecef6a65a"
CONTENT = "4c4b714832d1989740a6f07dce058c11aa1e9123056966ede06ce42d1df182bd"
COMPANION = "bb-agent-companion.v1"
RAW = "a" * 64


def _compat(*, allow_debug=False):
    return LiveCompatibility(
        GAME_VERSION,
        CONTENT,
        expected_mods=(),
        expected_companion_version=COMPANION,
        allow_debug=allow_debug,
    )


def _stream(**changes):
    values = dict(
        record_type=LiveRecordType.STREAM_START,
        companion_version=COMPANION,
        runtime_game_version="runtime-test",
        ruleset_game_version=GAME_VERSION,
        ruleset_content_fingerprint=CONTENT,
        mods=(),
    )
    values.update(changes)
    return LiveRecord(**values)


def _ready(generation=1, **changes):
    values = dict(
        record_type=LiveRecordType.DECISION_READY,
        companion_version=COMPANION,
        runtime_game_version="runtime-test",
        ruleset_game_version=GAME_VERSION,
        ruleset_content_fingerprint=CONTENT,
        mods=(),
        battle_sequence=1,
        source_generation=generation,
        raw_source_fingerprint=RAW,
        information_profile="player_legal",
        payload={"fixture": "live", "generation": generation},
    )
    values.update(changes)
    return LiveRecord(**values)


def _invalidated(generation=1, reason="action_resolving", **changes):
    values = dict(
        record_type=LiveRecordType.DECISION_INVALIDATED,
        companion_version=COMPANION,
        runtime_game_version="runtime-test",
        ruleset_game_version=GAME_VERSION,
        ruleset_content_fingerprint=CONTENT,
        mods=(),
        battle_sequence=1,
        source_generation=generation,
        reason=reason,
    )
    values.update(changes)
    return LiveRecord(**values)


def _html(record):
    return f'<div class="text">{encode_live_frame(record)}</div>'


def test_live_frame_round_trip_and_integrity_fail_closed() -> None:
    record = _ready(payload={"nested": [1, {"x": "@<>"}], "ok": True})
    frame = encode_live_frame(record)

    decoded = decode_live_frame(frame)
    assert decoded.to_wire_dict() == record.to_wire_dict()
    assert decoded.to_wire_dict()["payload"] == record.to_wire_dict()["payload"]
    assert LIVE_ENVELOPE_VERSION in json.dumps(decoded.to_wire_dict())
    assert LIVE_CAPTURE_VERSION in json.dumps(decoded.to_wire_dict())

    prefix, size, digest, body = frame.split("|", 3)
    assert prefix == "BBAGENT1"
    assert len(digest) == 64
    with pytest.raises(ValueError, match="length mismatch"):
        decode_live_frame("|".join((prefix, str(int(size) + 1), digest, body)))
    bad_digest = "0" * 64 if digest != "0" * 64 else "1" * 64
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        decode_live_frame("|".join((prefix, size, bad_digest, body)))
    with pytest.raises(ValueError, match="malformed live frame"):
        decode_live_frame(frame[:-1] + "!")


def test_live_frame_strict_schema_and_size_limits() -> None:
    frame = encode_live_frame(_ready())
    with pytest.raises(ValueError, match="encoded size"):
        decode_live_frame(frame, max_encoded_bytes=8)
    with pytest.raises(ValueError, match="decoded size"):
        decode_live_frame(frame, max_decoded_bytes=8)

    wire = _ready().to_wire_dict()
    wire["unexpected"] = True
    raw = json.dumps(wire, sort_keys=True, separators=(",", ":")).encode()
    encoded = __import__("base64").urlsafe_b64encode(raw).decode().rstrip("=")
    digest = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="fields do not match strict schema"):
        decode_live_frame(f"BBAGENT1|{len(raw)}|{digest}|{encoded}")


def test_live_frame_rejects_noncanonical_and_duplicate_json() -> None:
    wire = _ready().to_wire_dict()
    canonical = json.dumps(wire, sort_keys=True, separators=(",", ":")).encode()
    noncanonical = json.dumps(wire, sort_keys=False, indent=1).encode()
    assert noncanonical != canonical

    def frame(raw: bytes) -> str:
        encoded = __import__("base64").urlsafe_b64encode(raw).decode().rstrip("=")
        return f"BBAGENT1|{len(raw)}|{hashlib.sha256(raw).hexdigest()}|{encoded}"

    with pytest.raises(ValueError, match="not canonical JSON"):
        decode_live_frame(frame(noncanonical))

    duplicate = canonical[:-1] + b',"mods":[]}'
    with pytest.raises(ValueError, match="duplicate live JSON field: mods"):
        decode_live_frame(frame(duplicate))


def test_kernel_identity_pins_profile_policy_and_manifest_fingerprints() -> None:
    identity = current_live_kernel_identity()
    for value in (
        identity.evaluation_profile_fingerprint,
        identity.unit_value_policy_fingerprint,
        identity.mechanics_manifest_fingerprint,
    ):
        assert len(value) == 64
        int(value, 16)
    assert identity.unit_value_policy_version == "m1-common-preservation.v1"


def test_machine_orders_invalidates_deduplicates_and_conflicts() -> None:
    ids = iter(("stream-a", "stream-b"))
    machine = LiveIngestMachine(_compat(), stream_id_factory=lambda: next(ids))

    assert machine.accept(_ready()).status is LiveIngestStatus.REJECTED_STALE
    start = machine.accept(_stream())
    assert start.status is LiveIngestStatus.STREAM_STARTED
    assert machine.capture_stream_id == "stream-a"

    first = machine.accept(_ready(1))
    assert first.status is LiveIngestStatus.READY
    assert first.decision is not None
    assert machine.current_decision == first.decision

    duplicate = machine.accept(_ready(1))
    assert duplicate.status is LiveIngestStatus.DUPLICATE
    assert duplicate.decision == first.decision

    changed = _ready(1, payload={"fixture": "changed"})
    conflict = machine.accept(changed)
    assert conflict.status is LiveIngestStatus.REJECTED_CONFLICT
    assert machine.current_decision is None
    assert machine.accept(_ready(1)).status is LiveIngestStatus.REJECTED_STALE

    # A fresh stream clears the conflict and all prior ordering state.
    assert machine.accept(_stream()).status is LiveIngestStatus.STREAM_STARTED
    assert machine.capture_stream_id == "stream-b"
    assert machine.accept(_ready(2)).status is LiveIngestStatus.READY
    assert machine.accept(_ready(1)).status is LiveIngestStatus.REJECTED_STALE

    invalidated = machine.accept(_invalidated(2))
    assert invalidated.status is LiveIngestStatus.INVALIDATED
    assert machine.current_decision is None
    assert machine.accept(_ready(1)).status is LiveIngestStatus.REJECTED_STALE
    assert machine.accept(_ready(3)).status is LiveIngestStatus.READY


def test_machine_rejects_compatibility_and_debug_by_default() -> None:
    machine = LiveIngestMachine(_compat(), stream_id_factory=lambda: "stream")
    wrong = _stream(ruleset_game_version="wrong")
    assert machine.accept(wrong).status is LiveIngestStatus.REJECTED_INCOMPATIBLE
    runtime_checked = LiveIngestMachine(
        LiveCompatibility(
            GAME_VERSION,
            CONTENT,
            expected_mods=(),
            expected_companion_version=COMPANION,
            expected_runtime_game_version="runtime-good",
        ),
        stream_id_factory=lambda: "runtime-stream",
    )
    assert (
        runtime_checked.accept(_stream(runtime_game_version="runtime-wrong")).status
        is LiveIngestStatus.REJECTED_INCOMPATIBLE
    )
    assert machine.accept(_stream()).status is LiveIngestStatus.STREAM_STARTED

    debug = _ready(information_profile="omniscient_debug")
    rejected = machine.accept(debug)
    assert rejected.status is LiveIngestStatus.REJECTED_INCOMPATIBLE
    assert machine.current_decision is None

    debug_machine = LiveIngestMachine(
        _compat(allow_debug=True), stream_id_factory=lambda: "stream-debug"
    )
    debug_machine.accept(_stream())
    assert debug_machine.accept(debug).status is LiveIngestStatus.READY


def test_machine_persistence_restores_current_ready_payload() -> None:
    machine = LiveIngestMachine(_compat(), stream_id_factory=lambda: "stream")
    machine.accept(_stream())
    accepted = machine.accept(_ready(4))
    assert accepted.decision is not None

    restored = LiveIngestMachine.from_persisted_dict(
        _compat(), machine.to_persisted_dict(), stream_id_factory=lambda: "unused"
    )
    assert restored.capture_stream_id == "stream"
    assert restored.current_decision == accepted.decision
    assert restored.accept(_ready(3)).status is LiveIngestStatus.REJECTED_STALE
    duplicate = restored.accept(_ready(4))
    assert duplicate.status is LiveIngestStatus.DUPLICATE
    assert duplicate.decision == accepted.decision


def test_invalidation_same_generation_only_restores_exact_prior_ready() -> None:
    machine = LiveIngestMachine(_compat(), stream_id_factory=lambda: "stream")
    machine.accept(_stream())
    original = machine.accept(_ready(2))
    assert original.status is LiveIngestStatus.READY

    assert machine.accept(_invalidated(2)).status is LiveIngestStatus.INVALIDATED
    assert machine.current_decision is None

    restored = machine.accept(_ready(2))
    assert restored.status is LiveIngestStatus.DUPLICATE
    assert restored.decision == original.decision
    assert machine.current_decision == original.decision

    assert machine.accept(_invalidated(2)).status is LiveIngestStatus.INVALIDATED
    changed_source = machine.accept(_ready(2, raw_source_fingerprint="b" * 64))
    assert changed_source.status is LiveIngestStatus.REJECTED_CONFLICT
    assert machine.current_decision is None

    fresh = LiveIngestMachine(_compat(), stream_id_factory=lambda: "fresh")
    fresh.accept(_stream())
    fresh.accept(_invalidated(3))
    assert fresh.accept(_ready(3)).status is LiveIngestStatus.REJECTED_STALE
    assert fresh.accept(_ready(4)).status is LiveIngestStatus.READY


def test_machine_rejects_stale_kernel_identity() -> None:
    machine = LiveIngestMachine(_compat(), stream_id_factory=lambda: "stream")
    stale = replace(current_live_kernel_identity(), evaluation_config="stale-profile")
    rejected = machine.accept(_stream(kernel_identity=stale))
    assert rejected.status is LiveIngestStatus.REJECTED_INCOMPATIBLE
    assert "kernel compatibility" in rejected.message
    assert machine.capture_stream_id is None


def test_persisted_invalidation_retains_exact_reemit_identity() -> None:
    machine = LiveIngestMachine(_compat(), stream_id_factory=lambda: "stream")
    machine.accept(_stream())
    accepted = machine.accept(_ready(7))
    assert accepted.decision is not None
    machine.accept(_invalidated(7))

    restored = LiveIngestMachine.from_persisted_dict(
        _compat(), machine.to_persisted_dict(), stream_id_factory=lambda: "unused"
    )
    assert restored.current_decision is None
    duplicate = restored.accept(_ready(7))
    assert duplicate.status is LiveIngestStatus.DUPLICATE
    assert duplicate.decision is not None


def test_tailer_first_attach_uses_latest_stream_and_complete_divs(
    tmp_path: Path,
) -> None:
    log = tmp_path / "log.html"
    state = tmp_path / "ingest.json"
    log.write_text(
        "noise"
        + _html(_stream())
        + _html(_ready(1))
        + _html(_stream())
        + _html(_ready(5))
        + '<div class="text">BBAGENT1|999|',
        encoding="utf-8",
    )
    ids = iter(("old-stream", "current-stream"))
    tailer = LiveLogTailer(log, state, _compat(), stream_id_factory=lambda: next(ids))

    events = tailer.poll()
    assert [event.status for event in events] == [
        LiveIngestStatus.STREAM_STARTED,
        LiveIngestStatus.READY,
    ]
    assert tailer.current_decision is not None
    assert tailer.current_decision.capture_stream_id == "current-stream"
    assert tailer.current_decision.record.source_generation == 5
    assert all(event.frame_observed_ns is not None for event in events)
    assert all(event.canonical_available_ns is not None for event in events)
    assert all(
        event.processing_latency_ns is not None and event.processing_latency_ns >= 0
        for event in events
    )

    # Incomplete trailing HTML is not consumed or partially decoded.
    assert tailer.poll() == ()


def test_tailer_restart_resumes_cursor_with_current_ready_payload(
    tmp_path: Path,
) -> None:
    log = tmp_path / "log.html"
    state = tmp_path / "ingest.json"
    log.write_text(_html(_stream()) + _html(_ready(1)), encoding="utf-8")

    first = LiveLogTailer(log, state, _compat(), stream_id_factory=lambda: "stream")
    assert first.poll()[-1].status is LiveIngestStatus.READY
    assert first.current_decision is not None

    original = first.current_decision
    restarted = LiveLogTailer(
        log, state, _compat(), stream_id_factory=lambda: "should-not-be-used"
    )
    assert restarted.current_decision == original
    assert restarted.poll() == ()

    with log.open("a", encoding="utf-8") as handle:
        handle.write(_html(_ready(1)))
    events = restarted.poll()
    assert events[-1].status is LiveIngestStatus.DUPLICATE
    assert restarted.current_decision == original

    # A newer READY replaces the externally usable current payload.
    with log.open("a", encoding="utf-8") as handle:
        handle.write(_html(_ready(2)))
    assert restarted.poll()[-1].status is LiveIngestStatus.READY
    assert restarted.current_decision is not None


def test_tailer_truncation_is_discontinuity_and_waits_for_new_stream(
    tmp_path: Path,
) -> None:
    log = tmp_path / "log.html"
    state = tmp_path / "ingest.json"
    log.write_text(_html(_stream()) + _html(_ready(1)), encoding="utf-8")
    ids = iter(("stream-a", "stream-b"))
    tailer = LiveLogTailer(log, state, _compat(), stream_id_factory=lambda: next(ids))
    tailer.poll()
    assert tailer.current_decision is not None

    log.write_text("new boot without marker", encoding="utf-8")
    event = tailer.poll()
    assert event[0].status is LiveIngestStatus.STREAM_DISCONTINUITY
    assert tailer.current_decision is None

    with log.open("a", encoding="utf-8") as handle:
        handle.write(_html(_ready(2)))
    assert tailer.poll()[-1].status is LiveIngestStatus.REJECTED_STALE
    assert tailer.current_decision is None

    with log.open("a", encoding="utf-8") as handle:
        handle.write(_html(_stream()))
        handle.write(_html(_ready(1)))
    events = tailer.poll()
    assert [event.status for event in events] == [
        LiveIngestStatus.STREAM_STARTED,
        LiveIngestStatus.READY,
    ]
    assert tailer.current_decision is not None
    assert tailer.current_decision.capture_stream_id == "stream-b"


def test_tailer_persisted_anchor_mismatch_fails_closed(tmp_path: Path) -> None:
    log = tmp_path / "log.html"
    state = tmp_path / "ingest.json"
    log.write_text(_html(_stream()) + _html(_ready(1)), encoding="utf-8")
    tailer = LiveLogTailer(log, state, _compat(), stream_id_factory=lambda: "stream")
    tailer.poll()

    data = bytearray(log.read_bytes())
    data[-1] = ord("X") if data[-1] != ord("X") else ord("Y")
    log.write_bytes(data)

    restarted = LiveLogTailer(
        log, state, _compat(), stream_id_factory=lambda: "new-stream"
    )
    events = restarted.poll()
    assert events[0].status is LiveIngestStatus.STREAM_DISCONTINUITY
    assert restarted.current_decision is None


def test_tailer_malformed_protocol_record_never_yields_decision(tmp_path: Path) -> None:
    log = tmp_path / "log.html"
    state = tmp_path / "ingest.json"
    good = encode_live_frame(_ready(1))
    prefix, size, digest, body = good.split("|", 3)
    malformed = "|".join((prefix, size, "0" * 64, body))
    log.write_text(
        _html(_stream()) + f'<div class="text">{malformed}</div>', encoding="utf-8"
    )
    tailer = LiveLogTailer(log, state, _compat(), stream_id_factory=lambda: "stream")
    events = tailer.poll()
    assert [event.status for event in events] == [
        LiveIngestStatus.STREAM_STARTED,
        LiveIngestStatus.REJECTED_MALFORMED,
    ]
    assert tailer.current_decision is None
