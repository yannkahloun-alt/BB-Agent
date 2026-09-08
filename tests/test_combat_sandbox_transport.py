from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest

from bb_agent.combat_sandbox import extract_latest_combat_sandbox
from bb_agent.serialization import canonical_json_bytes

PREFIX = "BBCOMBAT1"


def _chunk_lines(
    section: str,
    key: str,
    record: dict[str, object],
    *,
    battle: int = 1,
    generation: int = 2,
    chunk_chars: int = 17,
) -> list[str]:
    raw = canonical_json_bytes(record)
    digest = hashlib.sha256(raw).hexdigest()
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    chunks = [encoded[i : i + chunk_chars] for i in range(0, len(encoded), chunk_chars)]
    return [
        (
            f"{PREFIX}|{battle}|{generation}|{section}|{key}|{i}|"
            f"{len(chunks)}|{len(raw)}|{digest}|{chunk}"
        )
        for i, chunk in enumerate(chunks)
    ]


def _record(section: str, key: str) -> dict[str, object]:
    return {
        "section": section,
        "key": key,
        "schema_version": "bb-agent-combat-sandbox.v1",
        "payload": {"value": f"{section}:{key}"},
    }


def _log(lines: list[str]) -> str:
    return (
        "<html><body>"
        + "".join(f'<div class="text">{line}</div>' for line in lines)
        + "</body></html>"
    )


def _timed_row(timestamp: str, message: str) -> str:
    return (
        '<div class="row info"><div class="entry-container">'
        f'<div class="time">{timestamp}</div>'
        '<div class="tag">SQ</div>'
        f'<div class="text">{message}</div>'
        "</div></div>"
    )


def test_extract_reassembles_full_generation_by_section_and_key(
    tmp_path: Path,
) -> None:
    manifest = {
        "section": "manifest",
        "key": "root",
        "schema_version": "bb-agent-combat-sandbox.v1",
        "payload": {
            "expected_records": [
                "actor:actor:1",
                "manifest:root",
                "tile:tile:1:1",
            ],
        },
    }
    actor = _record("actor", "actor:1")
    tile = _record("tile", "tile:1:1")
    lines = (
        _chunk_lines("actor", "actor:1", actor)
        + _chunk_lines("tile", "tile:1:1", tile)
        + _chunk_lines("manifest", "root", manifest)
    )
    path = tmp_path / "log.html"
    path.write_text(_log(lines), encoding="utf-8")

    snapshot = extract_latest_combat_sandbox(path)
    assert snapshot["battle_sequence"] == 1
    assert snapshot["source_generation"] == 2
    assert snapshot["records"]["actor:actor:1"] == actor
    assert snapshot["records"]["tile:tile:1:1"] == tile
    assert snapshot["extraction_metrics"] == {
        "player_legal_build_begin_time": None,
        "player_legal_build_end_time": None,
        "player_legal_build_timestamp_span_seconds": None,
        "player_legal_build_same_timestamp_bucket": False,
    }


def test_extract_preserves_player_legal_build_timestamp_span(tmp_path: Path) -> None:
    manifest = {
        "section": "manifest",
        "key": "root",
        "schema_version": "bb-agent-combat-sandbox.v1",
        "payload": {"expected_records": ["manifest:root"]},
    }
    frame_log = _log(_chunk_lines("manifest", "root", manifest))
    path = tmp_path / "log.html"
    path.write_text(
        "<html><body>"
        + _timed_row(
            "23:59:59",
            "[BB-Agent Combat Sandbox] player_legal_build_begin "
            "battle=1 generation=2",
        )
        + _timed_row(
            "00:00:00",
            "[BB-Agent Combat Sandbox] player_legal_build_end battle=1 generation=2",
        )
        + frame_log.removeprefix("<html><body>").removesuffix("</body></html>")
        + "</body></html>",
        encoding="utf-8",
    )

    snapshot = extract_latest_combat_sandbox(path)
    assert snapshot["extraction_metrics"] == {
        "player_legal_build_begin_time": "23:59:59",
        "player_legal_build_end_time": "00:00:00",
        "player_legal_build_timestamp_span_seconds": 1,
        "player_legal_build_same_timestamp_bucket": False,
    }


def test_extract_rejects_missing_expected_record(tmp_path: Path) -> None:
    manifest = {
        "section": "manifest",
        "key": "root",
        "schema_version": "bb-agent-combat-sandbox.v1",
        "payload": {
            "expected_records": ["manifest:root", "tile:tile:1:1"],
        },
    }
    path = tmp_path / "log.html"
    path.write_text(
        _log(_chunk_lines("manifest", "root", manifest)),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing expected combat sandbox record"):
        extract_latest_combat_sandbox(path)


def test_extract_rejects_corrupt_chunk(tmp_path: Path) -> None:
    record = _record("manifest", "root")
    record["payload"] = {"expected_records": ["manifest:root"]}
    lines = _chunk_lines("manifest", "root", record)
    lines[-1] = lines[-1][:-1] + ("A" if lines[-1][-1] != "A" else "B")
    path = tmp_path / "log.html"
    path.write_text(_log(lines), encoding="utf-8")
    with pytest.raises(ValueError):
        extract_latest_combat_sandbox(path)
