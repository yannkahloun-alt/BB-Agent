from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest

from bb_agent.combat_sandbox import FRAME_PREFIX, extract_latest_combat_sandbox
from bb_agent.serialization import canonical_json_bytes


def _record(section: str, key: str, payload: object) -> dict[str, object]:
    return {
        "section": section,
        "key": key,
        "schema_version": "bb-agent-combat-sandbox.v1",
        "payload": payload,
    }


def _chunks(
    battle: int,
    generation: int,
    record: dict[str, object],
    size: int = 37,
) -> list[str]:
    raw = canonical_json_bytes(record)
    digest = hashlib.sha256(raw).hexdigest()
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    fragments = [
        encoded[index : index + size] for index in range(0, len(encoded), size)
    ] or [""]
    return [
        f"{FRAME_PREFIX}|{battle}|{generation}|{record['section']}|{record['key']}|"
        f"{index}|{len(fragments)}|{len(raw)}|{digest}|{fragment}"
        for index, fragment in enumerate(fragments)
    ]


def _log(path: Path, lines: list[str]) -> None:
    content = "".join(f'<div class="text">{line}</div>' for line in lines)
    path.write_text(
        "<html><body>" + content + "</body></html>",
        encoding="utf-8",
    )


def test_extract_accepts_sharded_manifest(tmp_path: Path) -> None:
    data_a = _record("tile", "tile:1:1", {"x": 1})
    data_b = _record("actor_core", "actor:7", {"hp": 50})
    shard = _record(
        "manifest_expected",
        "0",
        {"records": ["actor_core:actor:7", "tile:tile:1:1"]},
    )
    root = _record(
        "manifest",
        "root",
        {
            "expected_record_count": 2,
            "expected_shards": ["manifest_expected:0"],
        },
    )
    lines: list[str] = []
    for record in (data_a, data_b, shard, root):
        lines.extend(_chunks(1, 0, record))
    log = tmp_path / "log.html"
    _log(log, lines)

    snapshot = extract_latest_combat_sandbox(log)
    assert snapshot["records"]["tile:tile:1:1"]["payload"] == {"x": 1}
    assert snapshot["records"]["actor_core:actor:7"]["payload"] == {"hp": 50}


def test_extract_rejects_missing_expected_record_from_shard(
    tmp_path: Path,
) -> None:
    shard = _record("manifest_expected", "0", {"records": ["tile:tile:9:9"]})
    root = _record(
        "manifest",
        "root",
        {"expected_record_count": 1, "expected_shards": ["manifest_expected:0"]},
    )
    lines: list[str] = []
    for record in (shard, root):
        lines.extend(_chunks(1, 0, record))
    log = tmp_path / "log.html"
    _log(log, lines)

    with pytest.raises(ValueError, match="missing expected combat sandbox record"):
        extract_latest_combat_sandbox(log)


def test_extract_rejects_missing_manifest_shard(tmp_path: Path) -> None:
    root = _record(
        "manifest",
        "root",
        {"expected_record_count": 0, "expected_shards": ["manifest_expected:0"]},
    )
    log = tmp_path / "log.html"
    _log(log, _chunks(1, 0, root))

    with pytest.raises(ValueError, match="manifest shard is missing"):
        extract_latest_combat_sandbox(log)
