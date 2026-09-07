"""Decode and extract reusable Battle Brothers movement sandbox snapshots."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping
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


def decode_movement_sandbox_frame(
    frame: str | bytes,
    *,
    max_decoded_bytes: int = DEFAULT_MAX_DECODED_BYTES,
    max_encoded_bytes: int = DEFAULT_MAX_ENCODED_BYTES,
) -> dict[str, Any]:
    """Decode one integrity-framed movement sandbox record."""

    if max_decoded_bytes <= 0 or max_encoded_bytes <= 0:
        raise ValueError("sandbox frame size bounds must be positive")
    raw_frame = frame.encode("ascii") if isinstance(frame, str) else bytes(frame)
    if len(raw_frame) > max_encoded_bytes:
        raise ValueError("sandbox frame exceeds encoded size limit")

    match = _FRAME_RE.fullmatch(raw_frame)
    if match is None:
        raise ValueError("malformed movement sandbox frame")

    expected_length = int(match.group(1))
    if expected_length > max_decoded_bytes:
        raise ValueError("movement sandbox payload exceeds decoded size limit")

    expected_digest = match.group(2).decode("ascii")
    encoded = match.group(3)
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


def extract_latest_movement_sandbox(log_path: str | Path) -> dict[str, Any]:
    """Return the latest valid movement sandbox frame from Battle Brothers log.html."""

    path = Path(log_path)
    data = path.read_bytes()
    latest: dict[str, Any] | None = None
    prefix = (SANDBOX_FRAME_PREFIX + "|").encode("ascii")

    for match in _TEXT_DIV_RE.finditer(data):
        content = match.group(1).strip()
        if not content.startswith(prefix):
            continue
        latest = decode_movement_sandbox_frame(content)

    if latest is None:
        raise ValueError("no movement sandbox snapshot found in log")
    return latest
