from pathlib import Path

import pytest

from bb_agent.live_ingest import (
    LiveCompatibility,
    LiveIngestMachine,
    LiveIngestStatus,
    LiveLogTailer,
    LiveRecord,
    LiveRecordType,
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
        payload={"fixture": "live-hardening", "generation": generation},
    )
    values.update(changes)
    return LiveRecord(**values)


def _html(record):
    return f'<div class="text">{encode_live_frame(record)}</div>'


def test_incompatible_stream_start_clears_prior_stream() -> None:
    machine = LiveIngestMachine(_compat(), stream_id_factory=lambda: "stream-a")
    assert machine.accept(_stream()).status is LiveIngestStatus.STREAM_STARTED
    assert machine.accept(_ready()).status is LiveIngestStatus.READY
    assert machine.current_decision is not None

    rejected = machine.accept(_stream(ruleset_game_version="wrong"))
    assert rejected.status is LiveIngestStatus.REJECTED_INCOMPATIBLE
    assert machine.capture_stream_id is None
    assert machine.current_decision is None
    assert machine.accept(_ready(2)).status is LiveIngestStatus.REJECTED_STALE


def test_malformed_record_restart_stays_fail_closed_and_exact_ready_recovers(
    tmp_path: Path,
) -> None:
    log = tmp_path / "log.html"
    state = tmp_path / "ingest.json"
    log.write_text(_html(_stream()) + _html(_ready(1)), encoding="utf-8")

    tailer = LiveLogTailer(log, state, _compat(), stream_id_factory=lambda: "stream")
    assert tailer.poll()[-1].status is LiveIngestStatus.READY
    assert tailer.current_decision is not None

    good = encode_live_frame(_ready(1))
    prefix, size, _digest, body = good.split("|", 3)
    malformed = "|".join((prefix, size, "0" * 64, body))
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f'<div class="text">{malformed}</div>')

    events = tailer.poll()
    assert events[-1].status is LiveIngestStatus.REJECTED_MALFORMED
    assert tailer.current_decision is None

    restarted = LiveLogTailer(
        log, state, _compat(), stream_id_factory=lambda: "unused-stream"
    )
    assert restarted.current_decision is None
    assert restarted.poll() == ()

    with log.open("a", encoding="utf-8") as handle:
        handle.write(_html(_ready(1)))
    recovered = restarted.poll()
    assert recovered[-1].status is LiveIngestStatus.DUPLICATE
    assert restarted.current_decision is not None


def test_same_inode_truncate_and_regrow_detects_live_cursor_mismatch(
    tmp_path: Path,
) -> None:
    log = tmp_path / "log.html"
    state = tmp_path / "ingest.json"
    log.write_text(_html(_stream()) + _html(_ready(1)), encoding="utf-8")
    tailer = LiveLogTailer(log, state, _compat(), stream_id_factory=lambda: "stream")
    assert tailer.poll()[-1].status is LiveIngestStatus.READY
    assert tailer.current_decision is not None

    inode = log.stat().st_ino
    old_size = log.stat().st_size
    log.write_bytes(b"x" * old_size + _html(_ready(2)).encode("utf-8"))
    assert log.stat().st_ino == inode
    assert log.stat().st_size >= old_size

    events = tailer.poll()
    assert events[0].status is LiveIngestStatus.STREAM_DISCONTINUITY
    assert "live cursor anchor" in events[0].message
    assert tailer.current_decision is None


def test_debug_opt_in_policy_requires_boolean() -> None:
    with pytest.raises(ValueError, match="allow_debug must be a boolean"):
        LiveCompatibility(
            GAME_VERSION,
            CONTENT,
            expected_mods=(),
            expected_companion_version=COMPANION,
            allow_debug="false",
        )
