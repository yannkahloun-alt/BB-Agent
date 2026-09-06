from __future__ import annotations

from bb_agent.live_debug import LiveDebugTwinTracker
from bb_agent.live_ingest import (
    LiveRecord,
    LiveRecordType,
    decode_live_frame,
    encode_live_frame,
)

GAME_VERSION = "scripts-162f498ac7c49b4c317bbf54718a595ecef6a65a"
CONTENT = "4c4b714832d1989740a6f07dce058c11aa1e9123056966ede06ce42d1df182bd"
RAW = "a" * 64


def _ready(profile: str, payload: dict[str, object]) -> LiveRecord:
    return LiveRecord(
        record_type=LiveRecordType.DECISION_READY,
        companion_version="0.2.14",
        runtime_game_version="1.5.2.3",
        ruleset_game_version=GAME_VERSION,
        ruleset_content_fingerprint=CONTENT,
        mods=("mod_bb_agent_capture", "mod_modern_hooks"),
        battle_sequence=1,
        source_generation=7,
        raw_source_fingerprint=RAW,
        information_profile=profile,
        payload=payload,
    )


def test_debug_twin_pairs_same_raw_capture_without_merging_payloads() -> None:
    tracker = LiveDebugTwinTracker()
    debug = _ready("omniscient_debug", {"oracle_secret": "mdef:47"})
    legal = _ready("player_legal", {"enemy_mdef": {"representation": "UNKNOWN"}})

    assert tracker.accept(debug) is None
    twin = tracker.accept(legal)

    assert twin is not None
    assert twin.player_legal is legal
    assert twin.omniscient_debug is debug
    assert twin.raw_source_fingerprint == RAW
    assert tracker.current_twin == twin


def test_debug_twin_exact_duplicate_is_idempotent_but_conflict_fails() -> None:
    tracker = LiveDebugTwinTracker()
    debug = _ready("omniscient_debug", {"oracle_secret": "tile:20:30"})
    legal = _ready("player_legal", {"position": {"representation": "UNKNOWN"}})

    tracker.accept(debug)
    twin = tracker.accept(legal)
    assert twin is not None
    assert tracker.accept(debug) == twin

    changed = _ready("omniscient_debug", {"oracle_secret": "tile:99:99"})
    try:
        tracker.accept(changed)
    except ValueError as exc:
        assert "changed payload" in str(exc)
    else:
        raise AssertionError("conflicting debug twin must fail closed")


def test_oracle_only_sentinel_cannot_leak_through_player_legal_serialization() -> None:
    secret = "ORACLE_ONLY_SECRET_7f3b"
    legal = _ready(
        "player_legal",
        {"enemy_position": {"representation": "UNKNOWN", "value": None}},
    )
    debug = _ready("omniscient_debug", {"enemy_position_exact": secret})

    legal_frame = encode_live_frame(legal)
    debug_frame = encode_live_frame(debug)

    assert secret not in legal_frame
    assert secret in str(decode_live_frame(debug_frame).to_wire_dict())
    assert decode_live_frame(legal_frame).information_profile == "player_legal"
