from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest

from bb_agent.movement_sandbox import (
    SANDBOX_FRAME_PREFIX,
    decode_movement_sandbox_frame,
    extract_latest_movement_sandbox,
)
from bb_agent.serialization import canonical_json_bytes


def _frame(record: dict[str, object]) -> str:
    raw = canonical_json_bytes(record)
    digest = hashlib.sha256(raw).hexdigest()
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{SANDBOX_FRAME_PREFIX}|{len(raw)}|{digest}|{encoded}"


def _record(generation: int) -> dict[str, object]:
    return {
        "record_type": "MOVEMENT_SANDBOX",
        "schema_version": "bb-agent-movement-sandbox.v1",
        "battle_sequence": 1,
        "source_generation": generation,
        "raw_source_fingerprint": "a" * 64,
        "runtime_game_version": "1.5.2.3",
        "ruleset_game_version": "1.5.2.3",
        "ruleset_content_fingerprint": "b" * 64,
        "companion_version": "0.2.22",
        "payload": {
            "player_legal_state": {"tiles": []},
            "movement_context": {"active_tile_id": "tile:1:1"},
        },
    }


def test_decode_movement_sandbox_frame_validates_integrity() -> None:
    record = _record(3)
    assert decode_movement_sandbox_frame(_frame(record)) == record

    frame = _frame(record)
    fields = frame.split("|")
    fields[2] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        decode_movement_sandbox_frame("|".join(fields))


def test_extract_latest_movement_sandbox_from_log(tmp_path: Path) -> None:
    first = _record(1)
    latest = _record(2)
    log = tmp_path / "log.html"
    log.write_text(
        "<html><body>"
        f'<div class="text">{_frame(first)}</div>'
        '<div class="text">ordinary log line</div>'
        f'<div class="text">{_frame(latest)}</div>'
        "</body></html>",
        encoding="utf-8",
    )

    assert extract_latest_movement_sandbox(log) == latest


def test_extract_requires_a_snapshot(tmp_path: Path) -> None:
    log = tmp_path / "log.html"
    log.write_text('<div class="text">nothing useful</div>', encoding="utf-8")
    with pytest.raises(ValueError, match="no movement sandbox snapshot"):
        extract_latest_movement_sandbox(log)


def test_decoder_rejects_wrong_record_type() -> None:
    record = _record(1)
    record["record_type"] = "DECISION_READY"
    with pytest.raises(ValueError, match="record type"):
        decode_movement_sandbox_frame(_frame(record))
