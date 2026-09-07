"""Decode and assemble full Battle Brothers combat sandbox snapshots."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from bb_agent.serialization import canonical_json_bytes

FRAME_PREFIX = "BBCOMBAT1"
SCHEMA_VERSION = "bb-agent-combat-sandbox.v1"
_TEXT_DIV_RE = re.compile(rb'<div class="text">(.*?)</div>', re.DOTALL)
_CHUNK_RE = re.compile(
    rb"BBCOMBAT1\|([0-9]+)\|([0-9]+)\|([^|]+)\|([^|]+)\|"
    rb"([0-9]+)\|([0-9]+)\|([0-9]+)\|([0-9a-f]{64})\|"
    rb"([A-Za-z0-9_-]+)$"
)


def _decode_record(
    chunks: list[bytes], expected_length: int, digest: str
) -> dict[str, Any]:
    encoded = b"".join(chunks)
    padding = b"=" * ((4 - len(encoded) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(encoded + padding)
    except Exception as exc:  # pragma: no cover
        raise ValueError("combat sandbox base64 decode failed") from exc
    if len(raw) != expected_length:
        raise ValueError("combat sandbox payload length mismatch")
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("combat sandbox payload SHA-256 mismatch")
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("combat sandbox JSON decode failed") from exc
    if not isinstance(decoded, dict):
        raise ValueError("combat sandbox record root must be an object")
    if canonical_json_bytes(decoded) != raw:
        raise ValueError("combat sandbox record is not canonical JSON")
    if decoded.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("combat sandbox schema version mismatch")
    return decoded


def _manifest_expected_records(
    records: dict[str, dict[str, Any]], manifest: dict[str, Any]
) -> list[str]:
    payload = manifest.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("combat sandbox manifest payload is invalid")

    # Backward-compatible support for the initial one-record manifest format.
    direct = payload.get("expected_records")
    if direct is not None:
        if not isinstance(direct, list) or not all(
            isinstance(value, str) for value in direct
        ):
            raise ValueError("combat sandbox manifest expected_records is invalid")
        return direct

    shard_ids = payload.get("expected_shards")
    expected_count = payload.get("expected_record_count")
    if not isinstance(shard_ids, list) or not all(
        isinstance(value, str) for value in shard_ids
    ):
        raise ValueError("combat sandbox manifest expected_shards is invalid")
    if (
        not isinstance(expected_count, int)
        or isinstance(expected_count, bool)
        or expected_count < 0
    ):
        raise ValueError("combat sandbox manifest expected_record_count is invalid")

    expected: list[str] = []
    for shard_id in shard_ids:
        shard = records.get(shard_id)
        if shard is None:
            raise ValueError(f"combat sandbox manifest shard is missing: {shard_id}")
        shard_payload = shard.get("payload")
        shard_records = (
            shard_payload.get("records") if isinstance(shard_payload, dict) else None
        )
        if not isinstance(shard_records, list) or not all(
            isinstance(value, str) for value in shard_records
        ):
            raise ValueError(f"combat sandbox manifest shard is invalid: {shard_id}")
        expected.extend(shard_records)

    if len(expected) != expected_count:
        raise ValueError(
            "combat sandbox manifest expected-record count does not match shards"
        )
    if len(set(expected)) != len(expected):
        raise ValueError("combat sandbox manifest contains duplicate expected records")
    return expected


def extract_latest_combat_sandbox(log_path: str | Path) -> dict[str, Any]:
    """Assemble the latest complete combat-sandbox generation from log.html."""

    data = Path(log_path).read_bytes()
    grouped: dict[tuple[int, int], dict[tuple[str, str], dict[str, Any]]] = defaultdict(
        dict
    )

    for div in _TEXT_DIV_RE.finditer(data):
        content = div.group(1).strip()
        if not content.startswith((FRAME_PREFIX + "|").encode("ascii")):
            continue
        match = _CHUNK_RE.fullmatch(content)
        if match is None:
            continue
        battle = int(match.group(1))
        generation = int(match.group(2))
        section = match.group(3).decode("ascii")
        key = match.group(4).decode("ascii")
        index = int(match.group(5))
        count = int(match.group(6))
        expected_length = int(match.group(7))
        digest = match.group(8).decode("ascii")
        payload = match.group(9)
        if count <= 0 or index < 0 or index >= count:
            raise ValueError("combat sandbox chunk index/count is invalid")
        slot = grouped[(battle, generation)].setdefault(
            (section, key),
            {
                "count": count,
                "length": expected_length,
                "digest": digest,
                "chunks": {},
            },
        )
        if (
            slot["count"] != count
            or slot["length"] != expected_length
            or slot["digest"] != digest
        ):
            raise ValueError("combat sandbox chunk metadata conflict")
        chunks: dict[int, bytes] = slot["chunks"]
        if index in chunks:
            raise ValueError("duplicate combat sandbox chunk")
        chunks[index] = payload

    if not grouped:
        raise ValueError("no combat sandbox snapshot found in log")

    last_problem: ValueError | None = None
    for battle, generation in sorted(grouped, reverse=True):
        try:
            records: dict[str, dict[str, Any]] = {}
            for (section, key), slot in grouped[(battle, generation)].items():
                chunks = slot["chunks"]
                count = slot["count"]
                if len(chunks) != count or any(
                    index not in chunks for index in range(count)
                ):
                    raise ValueError("combat sandbox record has missing chunks")
                record = _decode_record(
                    [chunks[index] for index in range(count)],
                    slot["length"],
                    slot["digest"],
                )
                if record.get("section") != section or record.get("key") != key:
                    raise ValueError("combat sandbox section/key mismatch")
                records[f"{section}:{key}"] = record

            manifest = records.get("manifest:root")
            if manifest is None:
                raise ValueError("combat sandbox manifest is missing")
            expected = _manifest_expected_records(records, manifest)
            for record_id in expected:
                if record_id not in records:
                    raise ValueError(
                        f"missing expected combat sandbox record: {record_id}"
                    )
            return {
                "schema_version": SCHEMA_VERSION,
                "battle_sequence": battle,
                "source_generation": generation,
                "records": records,
            }
        except ValueError as exc:
            last_problem = exc

    if last_problem is not None:
        raise last_problem
    raise ValueError("no complete combat sandbox snapshot found in log")
