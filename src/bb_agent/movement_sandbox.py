"""Decode and extract reusable Battle Brothers movement sandbox snapshots."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from bb_agent.serialization import canonical_json_bytes

SANDBOX_FRAME_PREFIX = "BBSANDBOX1"
SANDBOX_SCHEMA_VERSION = "bb-agent-movement-sandbox.v1"
DEFAULT_MAX_DECODED_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_ENCODED_BYTES = 6 * 1024 * 1024
_FRAME_RE = re.compile(
    rb"BBSANDBOX1\|([0-9]+)\|([0-9a-f]{64})\|([A-Za-z0-9_-]+)$"
)
_CHUNK_RE = re.compile(
    rb"BBSANDBOX1\|([0-9]+)\|([0-9]+)\|([0-9]+)\|([0-9]+)\|"
    rb"([0-9]+)\|([0-9a-f]{64})\|([A-Za-z0-9_-]*)$"
)
_TEXT_DIV_RE = re.compile(rb'<div class="text">(.*?)</div>', re.DOTALL)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def _decode_payload(
    expected_length: int,
    expected_digest: str,
    encoded: bytes,
    *,
    max_decoded_bytes: int,
    max_encoded_bytes: int,
) -> dict[str, Any]:
    if expected_length > max_decoded_bytes:
        raise ValueError("movement sandbox payload exceeds decoded size limit")
    if len(encoded) > max_encoded_bytes:
        raise ValueError("movement sandbox payload exceeds encoded size limit")

    padding = b"=" * ((4 - len(encoded) % 4) % 4)
    try:
        payload = base64.urlsafe_b64decode(encoded + padding)
    except Exception as exc:  # pragma: no cover - defensive wrapper
        raise ValueError("movement sandbox base64 decode failed") from exc

    if len(payload) != expected_length:
        raise ValueError("movement sandbox payload length mismatch")
    if hashlib.sha256(payload).hexdigest() != expected_digest:
        raise ValueError("movement sandbox payload SHA-256 mismatch")

    try:
        decoded = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("movement sandbox JSON decode failed") from exc

    if not isinstance(decoded, dict):
        raise ValueError("movement sandbox payload root must be an object")
    if canonical_json_bytes(decoded) != payload:
        raise ValueError("movement sandbox payload is not canonical JSON")
    if decoded.get("record_type") != "MOVEMENT_SANDBOX":
        raise ValueError("movement sandbox record type mismatch")
    if decoded.get("schema_version") != SANDBOX_SCHEMA_VERSION:
        raise ValueError("movement sandbox schema version mismatch")
    if not isinstance(decoded.get("payload"), Mapping):
        raise ValueError("movement sandbox payload section must be an object")
    return decoded


def decode_movement_sandbox_frame(
    frame: str | bytes,
    *,
    max_decoded_bytes: int = DEFAULT_MAX_DECODED_BYTES,
    max_encoded_bytes: int = DEFAULT_MAX_ENCODED_BYTES,
) -> dict[str, Any]:
    """Decode the legacy one-line integrity-framed sandbox record."""

    if max_decoded_bytes <= 0 or max_encoded_bytes <= 0:
        raise ValueError("sandbox frame size bounds must be positive")
    raw_frame = frame.encode("ascii") if isinstance(frame, str) else bytes(frame)
    match = _FRAME_RE.fullmatch(raw_frame)
    if match is None:
        raise ValueError("malformed movement sandbox frame")
    return _decode_payload(
        int(match.group(1)),
        match.group(2).decode("ascii"),
        match.group(3),
        max_decoded_bytes=max_decoded_bytes,
        max_encoded_bytes=max_encoded_bytes,
    )


def decode_movement_sandbox_chunks(
    chunks: Sequence[str | bytes],
    *,
    max_decoded_bytes: int = DEFAULT_MAX_DECODED_BYTES,
    max_encoded_bytes: int = DEFAULT_MAX_ENCODED_BYTES,
) -> dict[str, Any]:
    """Reassemble and validate one ordered BBSANDBOX1 chunk set."""

    if max_decoded_bytes <= 0 or max_encoded_bytes <= 0:
        raise ValueError("sandbox frame size bounds must be positive")
    if not chunks:
        raise ValueError("no movement sandbox chunks supplied")

    metadata: tuple[int, int, int, int, str] | None = None
    fragments: dict[int, bytes] = {}
    for chunk in chunks:
        raw = chunk.encode("ascii") if isinstance(chunk, str) else bytes(chunk)
        match = _CHUNK_RE.fullmatch(raw)
        if match is None:
            raise ValueError("malformed movement sandbox chunk")

        battle = int(match.group(1))
        generation = int(match.group(2))
        index = int(match.group(3))
        count = int(match.group(4))
        expected_length = int(match.group(5))
        digest = match.group(6).decode("ascii")
        fragment = match.group(7)
        current = (battle, generation, count, expected_length, digest)

        if count <= 0 or index < 0 or index >= count:
            raise ValueError("movement sandbox chunk index/count is invalid")
        if metadata is None:
            metadata = current
        elif current != metadata:
            raise ValueError("movement sandbox chunk metadata conflict")
        if index in fragments:
            raise ValueError("duplicate movement sandbox chunk")
        fragments[index] = fragment

    assert metadata is not None
    battle, generation, count, expected_length, digest = metadata
    if len(fragments) != count:
        raise ValueError("missing movement sandbox chunk")
    encoded = b"".join(fragments[index] for index in range(count))
    decoded = _decode_payload(
        expected_length,
        digest,
        encoded,
        max_decoded_bytes=max_decoded_bytes,
        max_encoded_bytes=max_encoded_bytes,
    )
    if decoded.get("battle_sequence") != battle:
        raise ValueError("movement sandbox chunk battle identity mismatch")
    if decoded.get("source_generation") != generation:
        raise ValueError("movement sandbox chunk generation identity mismatch")
    return decoded


def extract_latest_movement_sandbox(log_path: str | Path) -> dict[str, Any]:
    """Return the latest complete valid movement sandbox from Battle Brothers log.html."""

    data = Path(log_path).read_bytes()
    latest: dict[str, Any] | None = None
    prefix = (SANDBOX_FRAME_PREFIX + "|").encode("ascii")
    pending: list[bytes] = []
    pending_count: int | None = None

    for match in _TEXT_DIV_RE.finditer(data):
        content = match.group(1).strip()
        if not content.startswith(prefix):
            continue

        chunk_match = _CHUNK_RE.fullmatch(content)
        if chunk_match is not None:
            index = int(chunk_match.group(3))
            count = int(chunk_match.group(4))
            if index == 0:
                if pending:
                    raise ValueError("missing movement sandbox chunk before next snapshot")
                pending = [content]
                pending_count = count
            else:
                if not pending or pending_count is None:
                    raise ValueError("movement sandbox chunk arrived without chunk zero")
                pending.append(content)

            if pending_count is not None and len(pending) == pending_count:
                latest = decode_movement_sandbox_chunks(pending)
                pending = []
                pending_count = None
            elif pending_count is not None and len(pending) > pending_count:
                raise ValueError("duplicate movement sandbox chunk")
            continue

        if pending:
            raise ValueError("missing movement sandbox chunk before legacy frame")
        latest = decode_movement_sandbox_frame(content)

    if pending:
        raise ValueError("missing movement sandbox chunk at end of log")
    if latest is None:
        raise ValueError("no movement sandbox snapshot found in log")
    return latest
